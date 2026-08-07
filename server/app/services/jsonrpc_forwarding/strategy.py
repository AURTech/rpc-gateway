import random
from collections.abc import Sequence
from statistics import median
from types import MappingProxyType
from typing import Protocol

from app.model.jsonrpc_forwarding import JsonRpcRouteCandidate
from app.model.jsonrpc_route import JsonRpcRoutingStrategyType
from app.model.runtime_state.endpoint.health import HealthStatus


class RoutingStrategy(Protocol):
    def select_next(self, candidates: Sequence[JsonRpcRouteCandidate]) -> JsonRpcRouteCandidate: ...


class PriorityFailoverStrategy:
    def select_next(self, candidates: Sequence[JsonRpcRouteCandidate]) -> JsonRpcRouteCandidate:
        if not candidates:
            raise ValueError('JSON-RPC routing strategy requires at least one candidate.')
        return min(candidates, key=lambda candidate: candidate.target.position)


class LoadBalanceStrategy:
    def __init__(self, random_source: random.Random | None = None) -> None:
        self._random = random_source or random.Random()

    def select_next(self, candidates: Sequence[JsonRpcRouteCandidate]) -> JsonRpcRouteCandidate:
        if not candidates:
            raise ValueError('JSON-RPC routing strategy requires at least one candidate.')
        if len(candidates) == 1:
            return candidates[0]
        weights: list[int] = []
        for candidate in candidates:
            if candidate.target.weight is None:
                raise ValueError('JSON-RPC load balance strategy requires candidate weights.')
            weights.append(candidate.target.weight)
        sampled = self._random.choices(candidates, weights=weights, k=2)
        if sampled[0] is sampled[1]:
            return sampled[0]
        first_unhealthy = self._is_unhealthy(sampled[0])
        second_unhealthy = self._is_unhealthy(sampled[1])
        if first_unhealthy != second_unhealthy:
            return sampled[1] if first_unhealthy else sampled[0]
        fallback_latency = self._fallback_latency(candidates)
        first_latency = self._latency(sampled[0], fallback_latency)
        second_latency = self._latency(sampled[1], fallback_latency)
        if first_latency == second_latency:
            return sampled[self._random.randrange(2)]
        return sampled[0] if first_latency < second_latency else sampled[1]

    @staticmethod
    def _fallback_latency(candidates: Sequence[JsonRpcRouteCandidate]) -> float:
        values = [
            candidate.health.latency_ms
            for candidate in candidates
            if candidate.health is not None and candidate.health.latency_ms is not None
        ]
        return float(median(values)) if values else 0.0

    @staticmethod
    def _latency(candidate: JsonRpcRouteCandidate, fallback: float) -> float:
        if candidate.health is None or candidate.health.latency_ms is None:
            return fallback
        return candidate.health.latency_ms

    @staticmethod
    def _is_unhealthy(candidate: JsonRpcRouteCandidate) -> bool:
        return candidate.health is not None and candidate.health.status is HealthStatus.UNHEALTHY


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
