import random
from collections.abc import Sequence
from types import MappingProxyType
from typing import Protocol

from app.model.jsonrpc_forwarding import JsonRpcRouteTarget
from app.model.jsonrpc_route import JsonRpcRoutingStrategyType


class RoutingStrategy(Protocol):
    def select_next(self, candidates: Sequence[JsonRpcRouteTarget]) -> JsonRpcRouteTarget: ...


class PriorityFailoverStrategy:
    def select_next(self, candidates: Sequence[JsonRpcRouteTarget]) -> JsonRpcRouteTarget:
        if not candidates:
            raise ValueError('JSON-RPC routing strategy requires at least one candidate.')
        return min(candidates, key=lambda candidate: candidate.position)


class LoadBalanceStrategy:
    def __init__(self, random_source: random.Random | None = None) -> None:
        self._random = random_source or random.Random()

    def select_next(self, candidates: Sequence[JsonRpcRouteTarget]) -> JsonRpcRouteTarget:
        if not candidates:
            raise ValueError('JSON-RPC routing strategy requires at least one candidate.')
        if len(candidates) == 1:
            return candidates[0]
        weights: list[int] = []
        for candidate in candidates:
            if candidate.weight is None:
                raise ValueError('JSON-RPC load balance strategy requires candidate weights.')
            weights.append(candidate.weight)
        return self._random.choices(candidates, weights=weights, k=1)[0]


_STRATEGY_FACTORIES = MappingProxyType(
    {
        JsonRpcRoutingStrategyType.LOAD_BALANCE: LoadBalanceStrategy,
        JsonRpcRoutingStrategyType.PRIORITY_FAILOVER: PriorityFailoverStrategy,
    }
)


def build_strategy(strategy_type: JsonRpcRoutingStrategyType) -> RoutingStrategy:
    factory = _STRATEGY_FACTORIES.get(strategy_type)
    if factory is None:
        raise ValueError('JSON-RPC routing strategy is unsupported.')
    return factory()
