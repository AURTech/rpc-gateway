import random
from unittest.mock import Mock

import pytest
from app.model.jsonrpc_forwarding import JsonRpcRouteTarget
from app.model.jsonrpc_route import JsonRpcRoutingStrategyType
from app.services.jsonrpc_forwarding.strategy import LoadBalanceStrategy, PriorityFailoverStrategy, build_strategy
from tests.jsonrpc_forwarding.factories import make_endpoint


def _make_candidate(
    endpoint_id: str,
    *,
    position: int = 0,
    weight: int = 100,
) -> JsonRpcRouteTarget:
    return JsonRpcRouteTarget(endpoint=make_endpoint(endpoint_id), position=position, weight=weight)


def test_load_balance_selects_once_by_weight() -> None:
    first = _make_candidate('first', weight=20)
    second = _make_candidate('second', weight=80)
    candidates = [first, second]
    random_source: random.Random = Mock(spec=random.Random)
    random_source.choices.return_value = [first]

    selected = LoadBalanceStrategy(random_source=random_source).select_next(candidates)

    assert selected is first
    random_source.choices.assert_called_once_with(candidates, weights=[20, 80], k=1)


def test_load_balance_can_select_single_candidate() -> None:
    candidate = _make_candidate('only')

    selected = LoadBalanceStrategy(random_source=random.Random(0)).select_next([candidate])

    assert selected is candidate


def test_priority_failover_selects_lowest_position() -> None:
    backup = _make_candidate('backup', position=1)
    primary = _make_candidate('primary', position=0)

    selected = PriorityFailoverStrategy().select_next([backup, primary])

    assert selected is primary


def test_priority_failover_rejects_empty_candidates() -> None:
    with pytest.raises(ValueError, match='requires at least one candidate'):
        PriorityFailoverStrategy().select_next([])


def test_build_strategy_supports_priority_failover() -> None:
    strategy = build_strategy(JsonRpcRoutingStrategyType.PRIORITY_FAILOVER)

    assert isinstance(strategy, PriorityFailoverStrategy)
