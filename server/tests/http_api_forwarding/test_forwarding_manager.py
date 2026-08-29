import asyncio
import random
from unittest.mock import Mock

import pytest
from app.core.errors import UnavailableError
from app.model.blockchain import Chain, Network
from app.model.endpoint import (
    EndpointAccessResult,
    EndpointAccessSuccess,
    EndpointDescriptor,
    EndpointHttpApiRequest,
    EndpointProtocol,
    EndpointRequest,
    EndpointResponse,
)
from app.model.http_api_forwarding import HttpApiForwardingSuccess, HttpApiRoutePlan, HttpApiRouteTarget
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.model.runtime_state.circuit import CircuitDecision, CircuitObservation, CircuitOutcome, CircuitState
from app.model.runtime_state.endpoint.health import HealthFailure, HealthObservation
from app.services.http_api_forwarding import HttpApiForwardingManager
from app.services.runtime_state.circuit import CircuitManager
from app.services.runtime_state.endpoint.health import HealthDispatcher


def _endpoint(endpoint_id: str, *, enabled: bool = True) -> EndpointDescriptor:
    return EndpointDescriptor(
        id=endpoint_id,
        account_id='account-1',
        chain=Chain.TRON,
        network=Network.MAINNET,
        protocol=EndpointProtocol.HTTP_API,
        enabled=enabled,
        version=1,
    )


def _response(status_code: int, body: bytes) -> EndpointAccessSuccess:
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
    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
    ) -> HttpApiRoutePlan | None:
        return None


class _HealthStub(HealthDispatcher):
    def __init__(self) -> None:
        self.observations: list[HealthObservation] = []

    def submit(self, observation: HealthObservation) -> bool:
        self.observations.append(observation)
        return True


class _CircuitStub(CircuitManager):
    def __init__(self, unavailable_endpoints: set[str]) -> None:
        self.unavailable_endpoints = unavailable_endpoints
        self.before_calls: list[str] = []
        self.records: list[CircuitOutcome] = []

    async def before_attempt(self, endpoint_id: str, endpoint_version: int) -> CircuitDecision:
        self.before_calls.append(endpoint_id)
        if endpoint_id in self.unavailable_endpoints:
            raise UnavailableError('Circuit state is unavailable.')
        return CircuitDecision(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            allowed=True,
            state=CircuitState.CLOSED,
            failures=0,
            epoch=0,
        )

    def submit(self, decision: CircuitDecision, observation: CircuitObservation) -> bool:
        self.records.append(observation.outcome)
        return True


def test_load_balance_selects_once_by_weight() -> None:
    random_source: random.Random = Mock(spec=random.Random)
    health = _HealthStub()
    manager = HttpApiForwardingManager(
        endpoint_access=_EndpointAccessStub([]),
        route_plans=_RoutePlanStub(),
        circuit=_CircuitStub(set()),
        health=health,
        max_attempts=1,
        random_source=random_source,
    )
    first = HttpApiRouteTarget(endpoint=_endpoint('first'), position=0, weight=20)
    second = HttpApiRouteTarget(endpoint=_endpoint('second'), position=1, weight=80)
    candidates = [first, second]
    random_source.choices.return_value = [first]

    selected = manager._select_next(HttpApiRoutingStrategyType.LOAD_BALANCE, candidates)

    assert selected is first
    random_source.choices.assert_called_once_with(candidates, weights=[20, 80], k=1)


@pytest.mark.anyio
async def test_priority_failover_bypasses_unavailable_circuit_admission() -> None:
    access = _EndpointAccessStub([_response(503, b'unavailable'), _response(200, b'{"ok":true}')])
    health = _HealthStub()
    circuit = _CircuitStub({'primary'})
    targets = tuple(
        HttpApiRouteTarget(endpoint=_endpoint(endpoint_id), position=position, weight=None)
        for position, endpoint_id in enumerate(('primary', 'backup'))
    )
    plan = HttpApiRoutePlan(
        id='route-1',
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.TRON,
        network=Network.MAINNET,
        strategy_type=HttpApiRoutingStrategyType.PRIORITY_FAILOVER,
        max_attempts=2,
        retry_policy=HttpApiRetryPolicy.IDEMPOTENT,
        targets=targets,
    )
    manager = HttpApiForwardingManager(
        endpoint_access=access,
        route_plans=_RoutePlanStub(),
        circuit=circuit,
        health=health,
        max_attempts=2,
    )

    result = await manager.forward(plan, EndpointHttpApiRequest(method='POST', path='/wallet/getnodeinfo'))

    assert isinstance(result, HttpApiForwardingSuccess)
    assert result.response.body == b'{"ok":true}'
    assert access.attempted == ['primary', 'backup']
    assert circuit.before_calls == ['primary', 'backup']
    assert circuit.records == [CircuitOutcome.SUCCESS]
    assert [observation.failure for observation in health.observations] == [HealthFailure.SERVER, None]


@pytest.mark.anyio
async def test_forwarding_skips_disabled_endpoint_before_circuit_admission() -> None:
    access = _EndpointAccessStub([_response(200, b'{"ok":true}')])
    health = _HealthStub()
    circuit = _CircuitStub(set())
    plan = HttpApiRoutePlan(
        id='route-1',
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.TRON,
        network=Network.MAINNET,
        strategy_type=HttpApiRoutingStrategyType.PRIORITY_FAILOVER,
        max_attempts=2,
        retry_policy=HttpApiRetryPolicy.IDEMPOTENT,
        targets=(
            HttpApiRouteTarget(endpoint=_endpoint('primary', enabled=False), position=0, weight=None),
            HttpApiRouteTarget(endpoint=_endpoint('backup'), position=1, weight=None),
        ),
    )
    manager = HttpApiForwardingManager(
        endpoint_access=access,
        route_plans=_RoutePlanStub(),
        circuit=circuit,
        health=health,
        max_attempts=2,
    )

    result = await manager.forward(plan, EndpointHttpApiRequest(method='POST', path='/wallet/getnodeinfo'))

    assert isinstance(result, HttpApiForwardingSuccess)
    assert access.attempted == ['backup']
    assert circuit.before_calls == ['backup']


@pytest.mark.anyio
async def test_forwarding_bypasses_unavailable_circuit_for_healthy_endpoint() -> None:
    access = _EndpointAccessStub([_response(200, b'{"ok":true}')])
    health = _HealthStub()
    circuit = _CircuitStub({'primary'})
    plan = HttpApiRoutePlan(
        id='route-1',
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.TRON,
        network=Network.MAINNET,
        strategy_type=HttpApiRoutingStrategyType.PRIORITY_FAILOVER,
        max_attempts=1,
        retry_policy=HttpApiRetryPolicy.SAFE_ONLY,
        targets=(HttpApiRouteTarget(endpoint=_endpoint('primary'), position=0, weight=None),),
    )
    manager = HttpApiForwardingManager(
        endpoint_access=access,
        route_plans=_RoutePlanStub(),
        circuit=circuit,
        health=health,
        max_attempts=1,
    )

    result = await manager.forward(plan, EndpointHttpApiRequest(method='POST', path='/wallet/getnodeinfo'))

    assert isinstance(result, HttpApiForwardingSuccess)
    assert access.attempted == ['primary']
    assert circuit.before_calls == ['primary']
    assert circuit.records == []
    assert len(health.observations) == 1
    assert health.observations[0].success is True


@pytest.mark.anyio
async def test_cancellation_skips_health_failure_and_closes_circuit_attempt() -> None:
    access = _CancelledEndpointAccessStub([])
    health = _HealthStub()
    circuit = _CircuitStub(set())
    plan = HttpApiRoutePlan(
        id='route-1',
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.TRON,
        network=Network.MAINNET,
        strategy_type=HttpApiRoutingStrategyType.PRIORITY_FAILOVER,
        max_attempts=1,
        retry_policy=HttpApiRetryPolicy.SAFE_ONLY,
        targets=(HttpApiRouteTarget(endpoint=_endpoint('primary'), position=0, weight=None),),
    )
    manager = HttpApiForwardingManager(
        endpoint_access=access,
        route_plans=_RoutePlanStub(),
        circuit=circuit,
        health=health,
        max_attempts=1,
    )

    with pytest.raises(asyncio.CancelledError):
        await manager.forward(plan, EndpointHttpApiRequest(method='POST', path='/wallet/getnodeinfo'))

    assert access.attempted == ['primary']
    assert health.observations == []
    assert circuit.records == [CircuitOutcome.IGNORED]
