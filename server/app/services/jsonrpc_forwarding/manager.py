import json
import time
from datetime import UTC, datetime

from fastlog import log

from app.core.errors import UnavailableError
from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.endpoint import EndpointAccessFailure, EndpointDescriptor, EndpointJsonRpcRequest
from app.model.jsonrpc_forwarding import (
    JsonRpcForwardingFailure,
    JsonRpcForwardingFailureCode,
    JsonRpcForwardingFailureReason,
    JsonRpcForwardingResult,
    JsonRpcForwardingSuccess,
    JsonRpcRoutePlan,
)
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse, parse_jsonrpc_response
from app.model.runtime_state.circuit import (
    CircuitDecision,
    CircuitObservation,
    CircuitOutcome,
    CircuitState,
    CircuitWorkloadClass,
)
from app.services.endpoint import EndpointAccess
from app.services.jsonrpc_forwarding.circuit import (
    classify_access_observation,
    classify_response_observation,
    classify_workload,
)
from app.services.jsonrpc_forwarding.health import (
    HEALTH_SUCCESS,
    classify_access_failure,
    classify_response_failure,
    submit_health,
)
from app.services.jsonrpc_forwarding.interface import EndpointHealthReader, JsonRpcRoutePlanProvider
from app.services.jsonrpc_forwarding.retry import can_retry_access, can_retry_response, is_internal_failure
from app.services.jsonrpc_forwarding.selector import select_candidates
from app.services.jsonrpc_forwarding.strategy import build_strategy
from app.services.public.jsonrpc.tip import extract_tip_observation
from app.services.runtime_state.circuit import CircuitManager
from app.services.runtime_state.endpoint.health import HealthDispatcher
from app.services.runtime_state.endpoint.tip import TipDispatcher


def _encode_call(call: JsonRpcCall) -> bytes:
    return json.dumps(call.to_payload(), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


class JsonRpcForwardingManager:
    def __init__(
        self,
        endpoint_access: EndpointAccess,
        route_plans: JsonRpcRoutePlanProvider,
        health_reader: EndpointHealthReader,
        circuit: CircuitManager,
        health: HealthDispatcher,
        *,
        max_attempts: int,
        trace_method_prefixes: tuple[str, ...] = ('debug_', 'trace_'),
        tip: TipDispatcher | None = None,
    ) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError('JSON-RPC forwarding attempt limit must be between 1 and 10.')
        self._endpoint_access = endpoint_access
        self._route_plans = route_plans
        self._health_reader = health_reader
        self._circuit = circuit
        self._health = health
        self._tip = tip
        self._max_attempts = max_attempts
        self._trace_method_prefixes = trace_method_prefixes

    async def forward_call(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
    ) -> JsonRpcForwardingResult:
        plan = await self.load_plan(
            account_id=account_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
            method=call.method,
        )
        if isinstance(plan, JsonRpcForwardingFailure):
            return plan
        return await self.forward(plan, call)

    async def load_plan(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
        method: str,
    ) -> JsonRpcRoutePlan | JsonRpcForwardingFailure:
        """Load one immutable plan without reading or mutating Endpoint Runtime State."""
        try:
            plan = await self._route_plans.load(
                account_id=account_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
                method=method,
            )
        except (RuntimeError, ValueError) as exc:
            log.error(f'JSON-RPC route plan is invalid | Gateway:{gateway_id} | Error:{exc!r}')
            return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.INTERNAL)
        if plan is None:
            return JsonRpcForwardingFailure(
                code=JsonRpcForwardingFailureCode.NO_ENDPOINT,
                reason=JsonRpcForwardingFailureReason.ROUTE_MISSING,
            )
        return plan

    async def forward(self, plan: JsonRpcRoutePlan, call: JsonRpcCall) -> JsonRpcForwardingResult:
        """Forward one call through a configured strategy and bounded failover policy.

        Valid JSON-RPC application errors are final results. Every Circuit-approved attempt submits
        exactly one Circuit outcome, while admission-unavailable attempts bypass Circuit recording
        and Health observations remain non-blocking.
        """
        if not plan.targets:
            return JsonRpcForwardingFailure(
                code=JsonRpcForwardingFailureCode.NO_ENDPOINT,
                reason=JsonRpcForwardingFailureReason.NO_TARGET,
            )

        endpoint_versions = [(target.endpoint.id, target.endpoint.version) for target in plan.targets]
        try:
            health_by_endpoint = await self._health_reader.get_many(endpoint_versions)
        except Exception as exc:
            log.warning(f'JSON-RPC route Health read failed | Gateway:{plan.gateway_id} | Error:{exc!r}')
            health_by_endpoint = {}
        candidates = select_candidates(plan, health_by_endpoint)
        if not candidates:
            return JsonRpcForwardingFailure(
                code=JsonRpcForwardingFailureCode.NO_ENDPOINT,
                reason=JsonRpcForwardingFailureReason.CANDIDATE_FILTERED,
            )
        try:
            strategy = build_strategy(plan.strategy_type)
        except ValueError as exc:
            log.error(f'JSON-RPC route strategy is invalid | Route:{plan.id} | Error:{exc!r}')
            return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.INTERNAL)

        request = EndpointJsonRpcRequest(content=_encode_call(call))
        workload_class = classify_workload(call.method, self._trace_method_prefixes)
        allow_missing_version = CHAIN_CATALOG[plan.chain].protocol is Protocol.UTXO
        attempts = 0
        circuit_open = 0
        probe_in_progress = 0
        attempt_limit = min(plan.max_attempts, self._max_attempts)
        while candidates and attempts < attempt_limit:
            candidate = strategy.select_next(candidates)
            candidates.remove(candidate)
            endpoint = candidate.target.endpoint
            decision: CircuitDecision | None = None
            try:
                if workload_class is CircuitWorkloadClass.STANDARD:
                    decision = await self._circuit.before_attempt(endpoint.id, endpoint.version)
                else:
                    decision = await self._circuit.before_scoped_attempt(endpoint.id, endpoint.version, workload_class)
            except UnavailableError as exc:
                log.warning(
                    f'JSON-RPC Circuit admission bypassed | Gateway:{plan.gateway_id} | Endpoint:{endpoint.id} | Error:{exc!r}'
                )
            if decision is not None and not decision.allowed:
                if decision.state is CircuitState.OPEN:
                    circuit_open += 1
                else:
                    probe_in_progress += 1
                continue

            attempts += 1
            observation = CircuitObservation(outcome=CircuitOutcome.IGNORED)
            try:
                started_at = time.perf_counter()
                result = await self._endpoint_access.execute(plan.account_id, endpoint.id, request)
                latency_ms = (time.perf_counter() - started_at) * 1000
                if isinstance(result, EndpointAccessFailure):
                    health = classify_access_failure(result.code)
                    submit_health(self._health, endpoint, latency_ms=latency_ms, classification=health)
                    if is_internal_failure(result.code):
                        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.INTERNAL)
                    observation = classify_access_observation(result.code, workload_class)
                    if can_retry_access(result.code, plan.retry_policy):
                        continue
                    return JsonRpcForwardingFailure(
                        code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED,
                        reason=JsonRpcForwardingFailureReason.ENDPOINT_FAILED,
                    )

                status_code = result.response.status_code
                if call.is_notification:
                    if 200 <= status_code < 300:
                        submit_health(self._health, endpoint, latency_ms=latency_ms, classification=HEALTH_SUCCESS)
                        observation = CircuitObservation(outcome=CircuitOutcome.SUCCESS)
                        return JsonRpcForwardingSuccess(response=None)
                    health = classify_response_failure(status_code)
                    submit_health(self._health, endpoint, latency_ms=latency_ms, classification=health)
                    observation = classify_response_observation(status_code, result.response.headers)
                    return JsonRpcForwardingFailure(
                        code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED,
                        reason=JsonRpcForwardingFailureReason.ENDPOINT_FAILED,
                    )

                try:
                    response = parse_jsonrpc_response(
                        result.response.body,
                        call.request_id(),
                        allow_missing_version=allow_missing_version,
                    )
                except ValueError:
                    health = classify_response_failure(status_code)
                    submit_health(self._health, endpoint, latency_ms=latency_ms, classification=health)
                    observation = classify_response_observation(status_code, result.response.headers)
                    if can_retry_response(status_code, plan.retry_policy, invalid_protocol=True):
                        continue
                    return JsonRpcForwardingFailure(
                        code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED,
                        reason=JsonRpcForwardingFailureReason.ENDPOINT_FAILED,
                    )
                if status_code in {425, 429}:
                    health = classify_response_failure(status_code)
                    submit_health(self._health, endpoint, latency_ms=latency_ms, classification=health)
                    observation = classify_response_observation(status_code, result.response.headers)
                    return JsonRpcForwardingSuccess(response=response)
                submit_health(self._health, endpoint, latency_ms=latency_ms, classification=HEALTH_SUCCESS)
                observation = CircuitObservation(outcome=CircuitOutcome.SUCCESS)
                if isinstance(response, JsonRpcSuccessResponse):
                    self._submit_tip(endpoint, call, response)
                return JsonRpcForwardingSuccess(response=response)
            finally:
                if decision is not None:
                    self._circuit.submit(decision, observation)

        if attempts:
            return JsonRpcForwardingFailure(
                code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED,
                reason=JsonRpcForwardingFailureReason.ENDPOINT_FAILED,
            )
        reason = (
            JsonRpcForwardingFailureReason.CIRCUIT_OPEN
            if circuit_open
            else JsonRpcForwardingFailureReason.PROBE_IN_PROGRESS
            if probe_in_progress
            else JsonRpcForwardingFailureReason.CANDIDATE_FILTERED
        )
        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT, reason=reason)

    def _submit_tip(
        self,
        endpoint: EndpointDescriptor,
        call: JsonRpcCall,
        response: JsonRpcSuccessResponse,
    ) -> None:
        if self._tip is None:
            return
        try:
            observation = extract_tip_observation(
                endpoint=endpoint,
                call=call,
                response=response,
                observed_at=datetime.now(UTC),
            )
            if observation is not None:
                self._tip.submit(observation)
        except Exception as exc:
            log.warning(f'JSON-RPC Tip observation failed | Endpoint:{endpoint.id} | Error:{exc!r}')
