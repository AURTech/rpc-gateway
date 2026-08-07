from dataclasses import dataclass

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointTrustLevel
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType
from app.model.runtime_state.endpoint.health import EndpointHealth


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcRouteTarget:
    endpoint: EndpointDescriptor
    position: int
    weight: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcRoutePlan:
    id: str
    account_id: str
    gateway_id: str
    chain: Chain
    network: Network
    strategy_type: JsonRpcRoutingStrategyType
    minimum_trust: EndpointTrustLevel
    max_latency_ms: float | None
    max_attempts: int
    retry_policy: JsonRpcRetryPolicy
    targets: tuple[JsonRpcRouteTarget, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcRouteCandidate:
    target: JsonRpcRouteTarget
    health: EndpointHealth | None
