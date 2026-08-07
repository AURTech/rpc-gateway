import random
from unittest.mock import Mock

import pytest
from app.model.jsonrpc_forwarding import JsonRpcRouteCandidate, JsonRpcRouteTarget
from app.model.jsonrpc_route import JsonRpcRoutingStrategyType
from app.model.runtime_state.endpoint.health import HealthStatus
from app.services.jsonrpc_forwarding.strategy import LoadBalanceStrategy, PriorityFailoverStrategy, build_strategy
from tests.jsonrpc_forwarding.factories import make_endpoint, make_health


def _make_candidate(
    endpoint_id: str,
    status: HealthStatus,
    latency_ms: float,
    *,
    position: int = 0,
) -> JsonRpcRouteCandidate:
    target = JsonRpcRouteTarget(endpoint=make_endpoint(endpoint_id), position=position, weight=100)
    return JsonRpcRouteCandidate(target=target, health=make_health(status, latency_ms))


def _make_strategy(first: JsonRpcRouteCandidate, second: JsonRpcRouteCandidate) -> LoadBalanceStrategy:
    random_source: random.Random = Mock(spec=random.Random)
    random_source.choices.return_value = [first, second]
    return LoadBalanceStrategy(random_source=random_source)


def test_load_balance_prefers_non_unhealthy_sample() -> None:
    unhealthy = _make_candidate('unhealthy', HealthStatus.UNHEALTHY, 1)
    healthy = _make_candidate('healthy', HealthStatus.HEALTHY, 100)

    selected = _make_strategy(unhealthy, healthy).select_next([unhealthy, healthy])

    assert selected is healthy


def test_load_balance_compares_latency_after_health() -> None:
    slow = _make_candidate('slow', HealthStatus.HEALTHY, 100)
    fast = _make_candidate('fast', HealthStatus.HEALTHY, 10)

    selected = _make_strategy(slow, fast).select_next([slow, fast])

    assert selected is fast


def test_load_balance_can_select_same_unhealthy_sample() -> None:
    unhealthy = _make_candidate('unhealthy', HealthStatus.UNHEALTHY, 10)
    healthy = _make_candidate('healthy', HealthStatus.HEALTHY, 20)

    selected = _make_strategy(unhealthy, unhealthy).select_next([unhealthy, healthy])

    assert selected is unhealthy


def test_load_balance_can_select_single_unhealthy_candidate() -> None:
    unhealthy = _make_candidate('unhealthy', HealthStatus.UNHEALTHY, 10)

    selected = LoadBalanceStrategy(random_source=random.Random(0)).select_next([unhealthy])

    assert selected is unhealthy


def test_priority_failover_selects_lowest_position_without_health_priority() -> None:
    backup = _make_candidate('backup', HealthStatus.HEALTHY, 1, position=1)
    primary = _make_candidate('primary', HealthStatus.UNHEALTHY, 100, position=0)

    selected = PriorityFailoverStrategy().select_next([backup, primary])

    assert selected is primary


def test_priority_failover_rejects_empty_candidates() -> None:
    with pytest.raises(ValueError, match='requires at least one candidate'):
        PriorityFailoverStrategy().select_next([])


def test_build_strategy_supports_priority_failover() -> None:
    strategy = build_strategy(JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)

    assert isinstance(strategy, PriorityFailoverStrategy)
