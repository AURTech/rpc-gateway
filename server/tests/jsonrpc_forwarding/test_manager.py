import asyncio
from collections.abc import Mapping

import pytest
from app.core.errors import UnavailableError
from app.model.blockchain import Chain, Network
from app.model.endpoint import (
    EndpointAccessResult,
    EndpointAccessSuccess,
    EndpointDescriptor,
    EndpointProtocol,
    EndpointRequest,
    EndpointResponse,
)
from app.model.jsonrpc_forwarding import (
    JsonRpcForwardingFailure,
    JsonRpcForwardingFailureCode,
    JsonRpcForwardingSuccess,
    JsonRpcRoutePlan,
)
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType
from app.model.public import JsonRpcCall
from app.model.runtime_state.circuit import CircuitDecision, CircuitObservation, CircuitOutcome, CircuitState
from app.model.runtime_state.endpoint.health import HealthFailure, HealthObservation
from app.model.runtime_state.endpoint.tip import TipObservation
from app.services.jsonrpc_forwarding.manager import JsonRpcForwardingManager
from app.services.runtime_state.circuit import CircuitManager
from app.services.runtime_state.endpoint.health import HealthDispatcher
from app.services.runtime_state.endpoint.tip import TipDispatcher
from tests.jsonrpc_forwarding.factories import make_endpoint, make_plan


def _make_plan(
    endpoint_ids: list[str],
    *,
    strategy_type: JsonRpcRoutingStrategyType = JsonRpcRoutingStrategyType.LOAD_BALANCE,
    retry_policy: JsonRpcRetryPolicy = JsonRpcRetryPolicy.SAFE_ONLY,
    max_attempts: int | None = None,
) -> JsonRpcRoutePlan:
    return make_plan(
        [make_endpoint(endpoint_id) for endpoint_id in endpoint_ids],
        strategy_type=strategy_type,
        retry_policy=retry_policy,
        max_attempts=max_attempts,
    )


def _make_response(status_code: int, body: bytes) -> EndpointAccessSuccess:
    return EndpointAccessSuccess(
        response=EndpointResponse(
            status_code=status_code,
            headers=(),
            body=body,
            request_bytes=1,
            response_bytes=len(body),
        )
    )


class _EndpointAccessStub:
    def __init__(self, results: list[EndpointAccessResult]) -> None:
        self._results = results
        self.attempted: list[str] = []

    async def get_descriptor(self, account_id: str, endpoint_id: str) -> EndpointDescriptor | None:
        return None

    async def list_descriptors(
        self,
        account_id: str,
        *,
        chain: Chain | None = None,
        network: Network | None = None,
        protocol: EndpointProtocol | None = None,
        enabled: bool | None = None,
    ) -> list[EndpointDescriptor]:
        return []

    async def execute(self, account_id: str, endpoint_id: str, request: EndpointRequest) -> EndpointAccessResult:
        self.attempted.append(endpoint_id)
        return self._results.pop(0)


class _CancelledEndpointAccessStub(_EndpointAccessStub):
    async def execute(self, account_id: str, endpoint_id: str, request: EndpointRequest) -> EndpointAccessResult:
        del account_id, request
        self.attempted.append(endpoint_id)
        raise asyncio.CancelledError


class _RoutePlanStub:
    def __init__(self, plan: JsonRpcRoutePlan) -> None:
        self._plan = plan

    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
        method: str,
    ) -> JsonRpcRoutePlan:
        return self._plan


class _HealthStateStub(HealthDispatcher):
    def __init__(self) -> None:
        self.observations: list[HealthObservation] = []

    def submit(self, observation: HealthObservation) -> bool:
        self.observations.append(observation)
        return True


class _CircuitStub(CircuitManager):
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        denied_endpoints: set[str] | None = None,
        unavailable_endpoints: set[str] | None = None,
        states: Mapping[str, CircuitState] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.denied_endpoints = denied_endpoints or set()
        self.unavailable_endpoints = unavailable_endpoints or set()
        self.states = states or {}
        self.failures = 0
        self.before_calls: list[str] = []
        self.records: list[CircuitOutcome] = []
        self.recorded_decisions: list[CircuitDecision] = []

    async def before_attempt(self, endpoint_id: str, endpoint_version: int) -> CircuitDecision:
        self.before_calls.append(endpoint_id)
        if endpoint_id in self.unavailable_endpoints:
            raise UnavailableError('Circuit state is unavailable.')
        if endpoint_id in self.denied_endpoints or self.failures >= self.failure_threshold:
            return CircuitDecision(
                endpoint_id=endpoint_id,
                endpoint_version=endpoint_version,
                allowed=False,
                state=CircuitState.OPEN,
                failures=self.failures,
                epoch=0,
            )
        state = self.states.get(endpoint_id, CircuitState.CLOSED)
        return CircuitDecision(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            allowed=True,
            state=state,
            failures=self.failures,
            epoch=0,
            probe_token='probe-token' if state is CircuitState.HALF_OPEN else None,
        )

    def submit(self, decision: CircuitDecision, observation: CircuitObservation) -> bool:
        self.recorded_decisions.append(decision)
        outcome = observation.outcome
        self.records.append(outcome)
        if outcome is CircuitOutcome.SAMPLED_FAILURE:
            self.failures += 1
        elif outcome is CircuitOutcome.SUCCESS:
            self.failures = 0
        return True


class _TipStateStub(TipDispatcher):
    def __init__(self) -> None:
        pass

    def submit(self, tip: TipObservation) -> bool:
        return True


def _make_forwarding(
    plan: JsonRpcRoutePlan,
    access: _EndpointAccessStub,
    health: _HealthStateStub,
    circuit: _CircuitStub,
) -> JsonRpcForwardingManager:
    return JsonRpcForwardingManager(
        endpoint_access=access,
        route_plans=_RoutePlanStub(plan),
        circuit=circuit,
        health=health,
        tip=_TipStateStub(),
        max_attempts=10,
    )


async def _forward(
    forwarding: JsonRpcForwardingManager, call: JsonRpcCall
) -> JsonRpcForwardingSuccess | JsonRpcForwardingFailure:
    return await forwarding.forward_call(
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
    )


@pytest.mark.anyio
async def test_valid_jsonrpc_error_is_success_despite_http_status() -> None:
    access = _EndpointAccessStub([_make_response(400, b'{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"bad"}}')])
    health = _HealthStateStub()
    circuit = _CircuitStub()
    forwarding = _make_forwarding(_make_plan(['endpoint-1']), access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_call', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert result.response is not None
    assert health.observations[0].success is True
    assert circuit.records == [CircuitOutcome.SUCCESS]


@pytest.mark.anyio
async def test_notification_failure_is_not_retried() -> None:
    access = _EndpointAccessStub(
        [
            _make_response(500, b''),
            _make_response(204, b''),
        ]
    )
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = _make_plan(['endpoint-1', 'endpoint-2'], retry_policy=JsonRpcRetryPolicy.IDEMPOTENT)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_sendRawTransaction'))

    assert result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)
    assert len(access.attempted) == 1
    assert health.observations[0].failure is HealthFailure.SERVER
    assert circuit.records == [CircuitOutcome.SAMPLED_FAILURE]


@pytest.mark.anyio
async def test_cancellation_skips_health_failure_and_closes_circuit_attempt() -> None:
    access = _CancelledEndpointAccessStub([])
    health = _HealthStateStub()
    circuit = _CircuitStub()
    forwarding = _make_forwarding(_make_plan(['endpoint-1']), access, health, circuit)

    with pytest.raises(asyncio.CancelledError):
        await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert access.attempted == ['endpoint-1']
    assert health.observations == []
    assert circuit.records == [CircuitOutcome.IGNORED]


@pytest.mark.anyio
async def test_invalid_auth_response_retries_without_circuit_failure() -> None:
    access = _EndpointAccessStub(
        [
            _make_response(401, b'unauthorized'),
            _make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'),
        ]
    )
    health = _HealthStateStub()
    circuit = _CircuitStub()
    forwarding = _make_forwarding(_make_plan(['endpoint-1', 'endpoint-2']), access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert len(access.attempted) == 2
    assert [observation.failure for observation in health.observations] == [HealthFailure.AUTH, None]
    assert circuit.records == [CircuitOutcome.IGNORED, CircuitOutcome.SUCCESS]


@pytest.mark.anyio
async def test_unhealthy_endpoint_still_opens_circuit_after_fifth_failure() -> None:
    responses: list[EndpointAccessResult] = []
    for _attempt in range(5):
        responses.append(_make_response(500, b'invalid'))
    access = _EndpointAccessStub(responses)
    health = _HealthStateStub()
    circuit = _CircuitStub(failure_threshold=5)
    forwarding = _make_forwarding(_make_plan(['endpoint-1']), access, health, circuit)
    call = JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1)

    results = [await _forward(forwarding, call) for _attempt in range(5)]
    denied = await _forward(forwarding, call)

    assert all(result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED) for result in results)
    assert circuit.failures == 5
    assert circuit.records == [CircuitOutcome.SAMPLED_FAILURE] * 5
    assert len(health.observations) == 5
    assert denied == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)
    assert len(access.attempted) == 5


@pytest.mark.anyio
async def test_priority_failover_primary_success_skips_backup() -> None:
    access = _EndpointAccessStub([_make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"primary"}')])
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = _make_plan(['primary', 'backup'], strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert access.attempted == ['primary']
    assert circuit.before_calls == ['primary']


@pytest.mark.anyio
async def test_forwarding_skips_disabled_endpoint_before_circuit_admission() -> None:
    access = _EndpointAccessStub([_make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"backup"}')])
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = make_plan(
        [make_endpoint('primary', enabled=False), make_endpoint('backup')],
        strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER,
    )
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert access.attempted == ['backup']
    assert circuit.before_calls == ['backup']


@pytest.mark.anyio
async def test_priority_failover_retries_backup_after_primary_failure() -> None:
    access = _EndpointAccessStub(
        [
            _make_response(500, b'invalid'),
            _make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"backup"}'),
        ]
    )
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = _make_plan(
        ['primary', 'backup'],
        strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER,
        retry_policy=JsonRpcRetryPolicy.IDEMPOTENT,
    )
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert access.attempted == ['primary', 'backup']
    assert result.attempted_endpoint_ids == ('primary', 'backup')
    assert circuit.records == [CircuitOutcome.SAMPLED_FAILURE, CircuitOutcome.SUCCESS]


@pytest.mark.anyio
async def test_forwarding_bypasses_unavailable_circuit_for_healthy_endpoint() -> None:
    access = _EndpointAccessStub([_make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"primary"}')])
    health = _HealthStateStub()
    circuit = _CircuitStub(unavailable_endpoints={'primary'})
    forwarding = _make_forwarding(_make_plan(['primary']), access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert access.attempted == ['primary']
    assert circuit.before_calls == ['primary']
    assert circuit.records == []
    assert len(health.observations) == 1
    assert health.observations[0].success is True


@pytest.mark.anyio
async def test_priority_failover_bypasses_unavailable_circuit_admission() -> None:
    access = _EndpointAccessStub(
        [
            _make_response(500, b'invalid'),
            _make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"backup"}'),
        ]
    )
    health = _HealthStateStub()
    circuit = _CircuitStub(unavailable_endpoints={'primary', 'backup'})
    plan = _make_plan(
        ['primary', 'backup'],
        strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER,
        retry_policy=JsonRpcRetryPolicy.IDEMPOTENT,
    )
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert access.attempted == ['primary', 'backup']
    assert circuit.before_calls == ['primary', 'backup']
    assert circuit.records == []
    assert [observation.failure for observation in health.observations] == [HealthFailure.SERVER, None]


@pytest.mark.anyio
async def test_unavailable_circuit_does_not_relax_safe_only_retry() -> None:
    access = _EndpointAccessStub([_make_response(500, b'invalid')])
    health = _HealthStateStub()
    circuit = _CircuitStub(unavailable_endpoints={'primary'})
    plan = _make_plan(['primary', 'backup'], strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_sendRawTransaction', id=1))

    assert result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)
    assert access.attempted == ['primary']
    assert circuit.before_calls == ['primary']
    assert circuit.records == []
    assert [observation.failure for observation in health.observations] == [HealthFailure.SERVER]


@pytest.mark.anyio
async def test_priority_failover_denied_primary_does_not_consume_attempt() -> None:
    access = _EndpointAccessStub([_make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"backup"}')])
    health = _HealthStateStub()
    circuit = _CircuitStub(denied_endpoints={'primary'})
    plan = _make_plan(
        ['primary', 'backup'],
        strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER,
        max_attempts=1,
    )
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert circuit.before_calls == ['primary', 'backup']
    assert access.attempted == ['backup']
    assert circuit.records == [CircuitOutcome.SUCCESS]


@pytest.mark.anyio
async def test_priority_failover_safe_only_stops_after_ambiguous_failure() -> None:
    access = _EndpointAccessStub([_make_response(500, b'invalid')])
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = _make_plan(['primary', 'backup'], strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_sendRawTransaction', id=1))

    assert result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)
    assert access.attempted == ['primary']
    assert circuit.before_calls == ['primary']


@pytest.mark.anyio
async def test_priority_failover_honors_max_attempts() -> None:
    access = _EndpointAccessStub(
        [
            _make_response(500, b'first'),
            _make_response(500, b'second'),
        ]
    )
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = _make_plan(
        ['primary', 'backup-1', 'backup-2'],
        strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER,
        retry_policy=JsonRpcRetryPolicy.IDEMPOTENT,
        max_attempts=2,
    )
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)
    assert access.attempted == ['primary', 'backup-1']
    assert circuit.before_calls == ['primary', 'backup-1']


@pytest.mark.anyio
async def test_priority_failover_all_denied_returns_no_endpoint() -> None:
    access = _EndpointAccessStub([])
    health = _HealthStateStub()
    circuit = _CircuitStub(denied_endpoints={'primary', 'backup'})
    plan = _make_plan(['primary', 'backup'], strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)
    assert circuit.before_calls == ['primary', 'backup']
    assert access.attempted == []
    assert circuit.records == []


@pytest.mark.anyio
async def test_priority_failover_executed_failure_is_attempts_failed() -> None:
    access = _EndpointAccessStub([_make_response(500, b'invalid')])
    health = _HealthStateStub()
    circuit = _CircuitStub()
    plan = _make_plan(['primary'], strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert result == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)
    assert access.attempted == ['primary']
    assert circuit.records == [CircuitOutcome.SAMPLED_FAILURE]


@pytest.mark.anyio
async def test_priority_failover_half_open_primary_recovers_before_backup() -> None:
    access = _EndpointAccessStub([_make_response(200, b'{"jsonrpc":"2.0","id":1,"result":"primary"}')])
    health = _HealthStateStub()
    circuit = _CircuitStub(states={'primary': CircuitState.HALF_OPEN})
    plan = _make_plan(['primary', 'backup'], strategy_type=JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)
    forwarding = _make_forwarding(plan, access, health, circuit)

    result = await _forward(forwarding, JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=1))

    assert isinstance(result, JsonRpcForwardingSuccess)
    assert access.attempted == ['primary']
    assert circuit.before_calls == ['primary']
    assert circuit.recorded_decisions[0].state is CircuitState.HALF_OPEN
    assert circuit.records == [CircuitOutcome.SUCCESS]
