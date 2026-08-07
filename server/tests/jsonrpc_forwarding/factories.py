from collections.abc import Sequence
from datetime import UTC, datetime

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointProtocol, EndpointTrustLevel
from app.model.jsonrpc_forwarding import JsonRpcRoutePlan, JsonRpcRouteTarget
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType
from app.model.runtime_state.endpoint.health import EndpointHealth, HealthStatus

OBSERVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def make_endpoint(
    endpoint_id: str,
    *,
    enabled: bool = True,
    trust_level: EndpointTrustLevel = EndpointTrustLevel.TRUSTED,
) -> EndpointDescriptor:
    return EndpointDescriptor(
        id=endpoint_id,
        account_id='account-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        enabled=enabled,
        trust_level=trust_level,
        version=1,
    )


def make_health(status: HealthStatus, latency_ms: float) -> EndpointHealth:
    return EndpointHealth(
        status=status,
        error_rate=0 if status is not HealthStatus.UNHEALTHY else 1,
        latency_ms=latency_ms,
        samples=3,
        last_observed_at=OBSERVED_AT,
    )


def make_plan(
    endpoints: Sequence[EndpointDescriptor],
    *,
    strategy_type: JsonRpcRoutingStrategyType = JsonRpcRoutingStrategyType.LOAD_BALANCE,
    retry_policy: JsonRpcRetryPolicy = JsonRpcRetryPolicy.SAFE_ONLY,
    max_attempts: int | None = None,
    max_latency_ms: int | None = None,
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
        minimum_trust=EndpointTrustLevel.TRUSTED,
        max_latency_ms=max_latency_ms,
        max_attempts=max_attempts if max_attempts is not None else len(endpoints),
        retry_policy=retry_policy,
        targets=targets,
    )
