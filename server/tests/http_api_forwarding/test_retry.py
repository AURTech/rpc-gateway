import pytest
from app.model.endpoint import EndpointAccessFailureCode
from app.model.http_api_route import HttpApiRetryPolicy
from app.services.http_api_forwarding import HttpApiForwardingManager


@pytest.mark.parametrize('status_code', [401, 403, 429, 300, 307])
def test_safe_policy_failover_statuses(status_code: int) -> None:
    assert HttpApiForwardingManager._retry_response(status_code, HttpApiRetryPolicy.SAFE_ONLY)


@pytest.mark.parametrize('status_code', [408, 425, 500, 503])
def test_ambiguous_statuses_require_idempotent_policy(status_code: int) -> None:
    assert not HttpApiForwardingManager._retry_response(status_code, HttpApiRetryPolicy.SAFE_ONLY)
    assert HttpApiForwardingManager._retry_response(status_code, HttpApiRetryPolicy.IDEMPOTENT)


@pytest.mark.parametrize(
    'code',
    [
        EndpointAccessFailureCode.NOT_FOUND,
        EndpointAccessFailureCode.DISABLED,
        EndpointAccessFailureCode.CONFIG_UNAVAILABLE,
        EndpointAccessFailureCode.TARGET_REJECTED,
        EndpointAccessFailureCode.CONNECTION_FAILED,
    ],
)
def test_safe_access_failures_can_failover(code: EndpointAccessFailureCode) -> None:
    assert HttpApiForwardingManager._retry_access(code, HttpApiRetryPolicy.SAFE_ONLY)


@pytest.mark.parametrize(
    'code',
    [
        EndpointAccessFailureCode.RESPONSE_FAILED,
        EndpointAccessFailureCode.RESPONSE_TOO_LARGE,
        EndpointAccessFailureCode.TIMEOUT,
    ],
)
def test_ambiguous_access_failures_require_idempotent_policy(code: EndpointAccessFailureCode) -> None:
    assert not HttpApiForwardingManager._retry_access(code, HttpApiRetryPolicy.SAFE_ONLY)
    assert HttpApiForwardingManager._retry_access(code, HttpApiRetryPolicy.IDEMPOTENT)
