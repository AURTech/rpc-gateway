from collections.abc import Sequence

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointProtocol
from app.model.jsonrpc_forwarding import JsonRpcRoutePlan, JsonRpcRouteTarget
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType


def make_endpoint(
    endpoint_id: str,
    *,
    enabled: bool = True,
) -> EndpointDescriptor:
    return EndpointDescriptor(
        id=endpoint_id,
        account_id='account-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        enabled=enabled,
        version=1,
    )


def make_plan(
    endpoints: Sequence[EndpointDescriptor],
    *,
    strategy_type: JsonRpcRoutingStrategyType = JsonRpcRoutingStrategyType.LOAD_BALANCE,
    retry_policy: JsonRpcRetryPolicy = JsonRpcRetryPolicy.SAFE_ONLY,
    max_attempts: int | None = None,
) -> JsonRpcRoutePlan:
    weight = 100 if strategy_type is JsonRpcRoutingStrategyType.LOAD_BALANCE else None
    targets = tuple(
        JsonRpcRouteTarget(endpoint=endpoint, position=position, weight=weight) for position, endpoint in enumerate(endpoints)
    )
    return JsonRpcRoutePlan(
        id='route-1',
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        strategy_type=strategy_type,
        max_attempts=max_attempts if max_attempts is not None else len(endpoints),
        retry_policy=retry_policy,
        targets=targets,
    )
