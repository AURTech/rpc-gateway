from collections.abc import Mapping

from app.model.endpoint import EndpointTrustLevel
from app.model.jsonrpc_forwarding import JsonRpcRouteCandidate, JsonRpcRoutePlan
from app.model.runtime_state.endpoint.health import EndpointHealth

_TRUST_ORDER: dict[EndpointTrustLevel, int] = {
    EndpointTrustLevel.UNVERIFIED: 0,
    EndpointTrustLevel.TRUSTED: 1,
    EndpointTrustLevel.AUTHORITATIVE: 2,
}


def select_candidates(
    plan: JsonRpcRoutePlan,
    health_by_endpoint: Mapping[str, EndpointHealth | None],
) -> list[JsonRpcRouteCandidate]:
    candidates: list[JsonRpcRouteCandidate] = []
    minimum_trust = _TRUST_ORDER[plan.minimum_trust]
    for target in plan.targets:
        endpoint = target.endpoint
        if not endpoint.enabled or _TRUST_ORDER[endpoint.trust_level] < minimum_trust:
            continue
        health = health_by_endpoint.get(endpoint.id)
        if (
            plan.max_latency_ms is not None
            and health is not None
            and health.latency_ms is not None
            and health.latency_ms > plan.max_latency_ms
        ):
            continue
        candidates.append(JsonRpcRouteCandidate(target=target, health=health))
    return candidates
