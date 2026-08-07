from dataclasses import dataclass
from enum import StrEnum

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointResponse, EndpointTrustLevel
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.model.runtime_state.endpoint.health import EndpointHealth


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiRouteTarget:
    endpoint: EndpointDescriptor
    position: int
    weight: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiRoutePlan:
    id: str
    account_id: str
    gateway_id: str
    chain: Chain
    network: Network
    strategy_type: HttpApiRoutingStrategyType
    minimum_trust: EndpointTrustLevel
    max_latency_ms: float | None
    max_attempts: int
    retry_policy: HttpApiRetryPolicy
    targets: tuple[HttpApiRouteTarget, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiRouteCandidate:
    target: HttpApiRouteTarget
    health: EndpointHealth | None


class HttpApiForwardingFailureCode(StrEnum):
    NO_ENDPOINT = 'no_endpoint'
    ATTEMPTS_FAILED = 'attempts_failed'
    INTERNAL = 'internal'


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiForwardingSuccess:
    response: EndpointResponse
    ok: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiForwardingFailure:
    code: HttpApiForwardingFailureCode
    response: EndpointResponse | None = None
    ok: bool = False


HttpApiForwardingResult = HttpApiForwardingSuccess | HttpApiForwardingFailure
