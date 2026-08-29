from dataclasses import dataclass, field
from enum import StrEnum

from app.model.public import JsonRpcResponse


class JsonRpcForwardingFailureCode(StrEnum):
    NO_ENDPOINT = 'no_endpoint'
    ATTEMPTS_FAILED = 'attempts_failed'
    INTERNAL = 'internal'


class JsonRpcForwardingFailureReason(StrEnum):
    ROUTE_MISSING = 'route_missing'
    NO_TARGET = 'no_target'
    CANDIDATE_FILTERED = 'candidate_filtered'
    CIRCUIT_OPEN = 'circuit_open'
    PROBE_IN_PROGRESS = 'probe_in_progress'
    ENDPOINT_FAILED = 'endpoint_failed'


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcForwardingSuccess:
    response: JsonRpcResponse | None
    attempted_endpoint_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcForwardingFailure:
    code: JsonRpcForwardingFailureCode
    reason: JsonRpcForwardingFailureReason | None = field(default=None, compare=False)
    attempted_endpoint_ids: tuple[str, ...] = field(default=(), compare=False)


JsonRpcForwardingResult = JsonRpcForwardingSuccess | JsonRpcForwardingFailure
