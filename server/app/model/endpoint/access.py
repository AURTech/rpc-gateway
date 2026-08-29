from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.model.blockchain import Chain, Network
from app.model.endpoint.endpoint import EndpointProtocol


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointDescriptor:
    id: str
    account_id: str
    chain: Chain
    network: Network
    protocol: EndpointProtocol
    enabled: bool
    version: int


# TODO(security): Apply trust-aware response admission outside protocol transport defaults.
@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointJsonRpcRequest:
    content: bytes
    timeout: float = 6
    max_response_bytes: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointHttpApiRequest:
    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    query: Mapping[str, str | int | bool] | Sequence[tuple[str, str | int | bool]] = field(default_factory=tuple)
    content: bytes | None = None
    timeout: float = 6
    max_response_bytes: int | None = None


EndpointRequest = EndpointJsonRpcRequest | EndpointHttpApiRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    request_bytes: int
    response_bytes: int


class EndpointAccessFailureCode(StrEnum):
    NOT_FOUND = 'not_found'
    DISABLED = 'disabled'
    PROTOCOL_MISMATCH = 'protocol_mismatch'
    CONFIG_UNAVAILABLE = 'config_unavailable'
    TARGET_REJECTED = 'target_rejected'
    INVALID_REQUEST = 'invalid_request'
    CONNECTION_FAILED = 'connection_failed'
    RESPONSE_FAILED = 'response_failed'
    TIMEOUT = 'timeout'
    RESPONSE_TOO_LARGE = 'response_too_large'


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointAccessSuccess:
    response: EndpointResponse
    ok: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointAccessFailure:
    code: EndpointAccessFailureCode
    ok: bool = False


EndpointAccessResult = EndpointAccessSuccess | EndpointAccessFailure
