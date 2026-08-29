from dataclasses import dataclass

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType


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
    max_attempts: int
    retry_policy: JsonRpcRetryPolicy
    targets: tuple[JsonRpcRouteTarget, ...]
