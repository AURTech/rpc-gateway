from app.model.endpoint import EndpointAccessFailureCode
from app.model.jsonrpc_route import JsonRpcRetryPolicy

_INTERNAL_FAILURES = frozenset(
    {
        EndpointAccessFailureCode.INVALID_REQUEST,
        EndpointAccessFailureCode.PROTOCOL_MISMATCH,
    }
)
_SAFE_FAILURES = frozenset(
    {
        EndpointAccessFailureCode.NOT_FOUND,
        EndpointAccessFailureCode.DISABLED,
        EndpointAccessFailureCode.CONFIG_UNAVAILABLE,
        EndpointAccessFailureCode.TARGET_REJECTED,
        EndpointAccessFailureCode.CONNECTION_FAILED,
    }
)
_AMBIGUOUS_FAILURES = frozenset(
    {
        EndpointAccessFailureCode.RESPONSE_FAILED,
        EndpointAccessFailureCode.RESPONSE_TOO_LARGE,
        EndpointAccessFailureCode.TIMEOUT,
    }
)
_IDEMPOTENT_HTTP_STATUSES = frozenset({408, 425, 429})


def is_internal_failure(code: EndpointAccessFailureCode) -> bool:
    return code in _INTERNAL_FAILURES


def can_retry_access(code: EndpointAccessFailureCode, policy: JsonRpcRetryPolicy) -> bool:
    if code in _SAFE_FAILURES:
        return True
    return policy is JsonRpcRetryPolicy.IDEMPOTENT and code in _AMBIGUOUS_FAILURES


def can_retry_response(
    status_code: int,
    policy: JsonRpcRetryPolicy,
    *,
    invalid_protocol: bool,
) -> bool:
    if status_code in (401, 403):
        return True
    retryable_status = status_code in _IDEMPOTENT_HTTP_STATUSES or 500 <= status_code < 600
    return policy is JsonRpcRetryPolicy.IDEMPOTENT and (invalid_protocol or retryable_status)
