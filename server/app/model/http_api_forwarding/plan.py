from dataclasses import dataclass
from enum import StrEnum

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointResponse
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType


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
    max_attempts: int
    retry_policy: HttpApiRetryPolicy
    targets: tuple[HttpApiRouteTarget, ...]


class HttpApiForwardingFailureCode(StrEnum):
    NO_ENDPOINT = 'no_endpoint'
    ATTEMPTS_FAILED = 'attempts_failed'
    INTERNAL = 'internal'


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiForwardingSuccess:
    response: EndpointResponse
    attempted_endpoint_ids: tuple[str, ...] = ()
    ok: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpApiForwardingFailure:
    code: HttpApiForwardingFailureCode
    response: EndpointResponse | None = None
    attempted_endpoint_ids: tuple[str, ...] = ()
    ok: bool = False


HttpApiForwardingResult = HttpApiForwardingSuccess | HttpApiForwardingFailure
