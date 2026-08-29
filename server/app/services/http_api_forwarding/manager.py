import random
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from fastlog import log

from app.core.errors import UnavailableError
from app.model.blockchain import Chain, Network
from app.model.endpoint import (
    EndpointAccessFailure,
    EndpointAccessFailureCode,
    EndpointDescriptor,
    EndpointHttpApiRequest,
    EndpointResponse,
)
from app.model.http_api_forwarding import (
    HttpApiForwardingFailure,
    HttpApiForwardingFailureCode,
    HttpApiForwardingResult,
    HttpApiForwardingSuccess,
    HttpApiRoutePlan,
    HttpApiRouteTarget,
)
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.model.runtime_state.circuit import CircuitDecision, CircuitObservation, CircuitOutcome
from app.model.runtime_state.endpoint.health import HealthFailure, HealthObservation, HealthOrigin
from app.services.endpoint import EndpointAccess
from app.services.endpoint.retry_after import parse_retry_after_seconds
from app.services.http_api_forwarding.interface import HttpApiRoutePlanProvider
from app.services.runtime_state.circuit import CircuitManager
from app.services.runtime_state.endpoint.health import HealthDispatcher

_SAFE_ACCESS_FAILURES = frozenset(
    {
        EndpointAccessFailureCode.NOT_FOUND,
        EndpointAccessFailureCode.DISABLED,
        EndpointAccessFailureCode.CONFIG_UNAVAILABLE,
        EndpointAccessFailureCode.TARGET_REJECTED,
        EndpointAccessFailureCode.CONNECTION_FAILED,
    }
)
_INTERNAL_ACCESS_FAILURES = frozenset({EndpointAccessFailureCode.INVALID_REQUEST, EndpointAccessFailureCode.PROTOCOL_MISMATCH})
_AMBIGUOUS_ACCESS_FAILURES = frozenset(
    {
        EndpointAccessFailureCode.RESPONSE_FAILED,
        EndpointAccessFailureCode.RESPONSE_TOO_LARGE,
        EndpointAccessFailureCode.TIMEOUT,
    }
)
_ALWAYS_RETRY_STATUSES = frozenset({401, 403, 429})
_IDEMPOTENT_RETRY_STATUSES = frozenset({408, 425})


class HttpApiForwardingManager:
    def __init__(
        self,
        endpoint_access: EndpointAccess,
        route_plans: HttpApiRoutePlanProvider,
        circuit: CircuitManager,
        health: HealthDispatcher,
        *,
        max_attempts: int,
        random_source: random.Random | None = None,
    ) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError('HTTP API forwarding attempt limit must be between 1 and 10.')
        self._endpoint_access = endpoint_access
        self._route_plans = route_plans
        self._circuit = circuit
        self._health = health
        self._max_attempts = max_attempts
        self._random = random_source or random.Random()

    async def load_plan(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
    ) -> HttpApiRoutePlan | HttpApiForwardingFailure:
        try:
            plan = await self._route_plans.load(account_id=account_id, gateway_id=gateway_id, chain=chain, network=network)
        except (RuntimeError, ValueError) as exc:
            log.error(f'HTTP API route plan is invalid | Gateway:{gateway_id} | Error:{exc!r}')
            return HttpApiForwardingFailure(code=HttpApiForwardingFailureCode.INTERNAL)
        if plan is None:
            return HttpApiForwardingFailure(code=HttpApiForwardingFailureCode.NO_ENDPOINT)
        return plan

    async def forward(self, plan: HttpApiRoutePlan, request: EndpointHttpApiRequest) -> HttpApiForwardingResult:
        """Forward with bounded attempts, bypassing Circuit recording only when admission is unavailable."""
        if not plan.targets:
            return HttpApiForwardingFailure(code=HttpApiForwardingFailureCode.NO_ENDPOINT)
        candidates = [target for target in plan.targets if target.endpoint.enabled]
        if plan.strategy_type is HttpApiRoutingStrategyType.LOAD_BALANCE and any(
            candidate.weight is None or candidate.weight <= 0 for candidate in candidates
        ):
            return HttpApiForwardingFailure(code=HttpApiForwardingFailureCode.INTERNAL)
        attempts = 0
        attempted_endpoint_ids: list[str] = []
        last_response: EndpointResponse | None = None
        attempt_limit = min(plan.max_attempts, self._max_attempts)
        while candidates and attempts < attempt_limit:
            candidate = self._select_next(plan.strategy_type, candidates)
            candidates.remove(candidate)
            endpoint = candidate.endpoint
            decision: CircuitDecision | None = None
            try:
                decision = await self._circuit.before_attempt(endpoint.id, endpoint.version)
            except UnavailableError as exc:
                log.warning(
                    f'HTTP API Circuit admission bypassed | Gateway:{plan.gateway_id} | Endpoint:{endpoint.id} | Error:{exc!r}'
                )
            if decision is not None and not decision.allowed:
                continue
            attempts += 1
            attempted_endpoint_ids.append(endpoint.id)
            observation = CircuitObservation(outcome=CircuitOutcome.IGNORED)
            started_at = time.perf_counter()
            try:
                result = await self._endpoint_access.execute(plan.account_id, endpoint.id, request)
                latency_ms = (time.perf_counter() - started_at) * 1000
                if isinstance(result, EndpointAccessFailure):
                    self._submit_access_health(endpoint, result.code, latency_ms)
                    observation = self._access_observation(result.code)
                    if result.code in _INTERNAL_ACCESS_FAILURES:
                        return HttpApiForwardingFailure(
                            code=HttpApiForwardingFailureCode.INTERNAL,
                            attempted_endpoint_ids=tuple(attempted_endpoint_ids),
                        )
                    if self._retry_access(result.code, plan.retry_policy):
                        continue
                    return HttpApiForwardingFailure(
                        code=HttpApiForwardingFailureCode.ATTEMPTS_FAILED,
                        attempted_endpoint_ids=tuple(attempted_endpoint_ids),
                    )
                response = result.response
                last_response = response
                self._submit_response_health(endpoint, response.status_code, latency_ms)
                observation = self._response_observation(response)
                if self._retry_response(response.status_code, plan.retry_policy):
                    continue
                return HttpApiForwardingSuccess(response=response, attempted_endpoint_ids=tuple(attempted_endpoint_ids))
            except Exception as exc:
                log.error(
                    f'HTTP API Endpoint attempt failed unexpectedly | Gateway:{plan.gateway_id} | '
                    f'Endpoint:{endpoint.id} | Error:{exc!r}'
                )
                return HttpApiForwardingFailure(
                    code=HttpApiForwardingFailureCode.INTERNAL,
                    attempted_endpoint_ids=tuple(attempted_endpoint_ids),
                )
            finally:
                if decision is not None:
                    self._circuit.submit(decision, observation)
        code = HttpApiForwardingFailureCode.ATTEMPTS_FAILED if attempts else HttpApiForwardingFailureCode.NO_ENDPOINT
        return HttpApiForwardingFailure(
            code=code,
            response=last_response,
            attempted_endpoint_ids=tuple(attempted_endpoint_ids),
        )

    def _select_next(
        self,
        strategy_type: HttpApiRoutingStrategyType,
        candidates: Sequence[HttpApiRouteTarget],
    ) -> HttpApiRouteTarget:
        if strategy_type is HttpApiRoutingStrategyType.PRIORITY_FAILOVER:
            return min(candidates, key=lambda candidate: candidate.position)
        weights = [candidate.weight or 0 for candidate in candidates]
        return self._random.choices(candidates, weights=weights, k=1)[0]

    @staticmethod
    def _retry_access(code: EndpointAccessFailureCode, policy: HttpApiRetryPolicy) -> bool:
        if code in _SAFE_ACCESS_FAILURES:
            return True
        return policy is HttpApiRetryPolicy.IDEMPOTENT and code in _AMBIGUOUS_ACCESS_FAILURES

    @staticmethod
    def _retry_response(status_code: int, policy: HttpApiRetryPolicy) -> bool:
        if status_code in _ALWAYS_RETRY_STATUSES or 300 <= status_code < 400:
            return True
        idempotent_status = status_code in _IDEMPOTENT_RETRY_STATUSES or 500 <= status_code < 600
        return policy is HttpApiRetryPolicy.IDEMPOTENT and idempotent_status

    def _submit_access_health(self, endpoint: EndpointDescriptor, code: EndpointAccessFailureCode, latency_ms: float) -> None:
        failure = {
            EndpointAccessFailureCode.CONNECTION_FAILED: HealthFailure.CONNECTION,
            EndpointAccessFailureCode.TIMEOUT: HealthFailure.TIMEOUT,
            EndpointAccessFailureCode.CONFIG_UNAVAILABLE: HealthFailure.CONFIG,
            EndpointAccessFailureCode.NOT_FOUND: HealthFailure.CONFIG,
            EndpointAccessFailureCode.DISABLED: HealthFailure.CONFIG,
        }.get(code, HealthFailure.PROTOCOL)
        self._submit_health(endpoint, latency_ms, failure)

    def _submit_response_health(self, endpoint: EndpointDescriptor, status_code: int, latency_ms: float) -> None:
        failure: HealthFailure | None = None
        if status_code in {401, 403}:
            failure = HealthFailure.AUTH
        elif status_code == 408:
            failure = HealthFailure.TIMEOUT
        elif 300 <= status_code < 400:
            failure = HealthFailure.PROTOCOL
        elif 500 <= status_code < 600:
            failure = HealthFailure.SERVER
        self._submit_health(endpoint, latency_ms, failure)

    def _submit_health(
        self,
        endpoint: EndpointDescriptor,
        latency_ms: float,
        failure: HealthFailure | None,
    ) -> None:
        self._health.submit(
            HealthObservation(
                endpoint_id=endpoint.id,
                endpoint_version=endpoint.version,
                origin=HealthOrigin.TRAFFIC,
                success=failure is None,
                failure=failure,
                latency_ms=latency_ms if failure is None else None,
                observed_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def _access_observation(code: EndpointAccessFailureCode) -> CircuitObservation:
        if code in {
            EndpointAccessFailureCode.CONNECTION_FAILED,
            EndpointAccessFailureCode.RESPONSE_FAILED,
            EndpointAccessFailureCode.TIMEOUT,
        }:
            return CircuitObservation(outcome=CircuitOutcome.HARD_FAILURE)
        return CircuitObservation(outcome=CircuitOutcome.IGNORED)

    @staticmethod
    def _response_observation(response: EndpointResponse) -> CircuitObservation:
        status_code = response.status_code
        if status_code in {425, 429}:
            return CircuitObservation(
                outcome=CircuitOutcome.THROTTLED,
                retry_after_seconds=parse_retry_after_seconds(response.headers),
            )
        if status_code == 408 or 500 <= status_code < 600:
            return CircuitObservation(outcome=CircuitOutcome.SAMPLED_FAILURE)
        if status_code in {401, 403}:
            return CircuitObservation(outcome=CircuitOutcome.IGNORED)
        if 200 <= status_code < 300 or 400 <= status_code < 500:
            return CircuitObservation(outcome=CircuitOutcome.SUCCESS)
        return CircuitObservation(outcome=CircuitOutcome.SAMPLED_FAILURE)
