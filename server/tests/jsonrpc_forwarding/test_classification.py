import pytest
from app.model.jsonrpc_route import JsonRpcRetryPolicy
from app.model.runtime_state.circuit import CircuitOutcome
from app.model.runtime_state.endpoint.health import HealthFailure
from app.services.jsonrpc_forwarding.circuit import classify_response_observation
from app.services.jsonrpc_forwarding.health import HealthDisposition, classify_response_failure
from app.services.jsonrpc_forwarding.retry import can_retry_response


@pytest.mark.parametrize(
    ('status_code', 'health_disposition', 'health_failure', 'circuit_outcome'),
    [
        (200, HealthDisposition.FAILURE, HealthFailure.PROTOCOL, CircuitOutcome.SAMPLED_FAILURE),
        (204, HealthDisposition.FAILURE, HealthFailure.PROTOCOL, CircuitOutcome.SAMPLED_FAILURE),
        (301, HealthDisposition.IGNORED, None, CircuitOutcome.IGNORED),
        (400, HealthDisposition.IGNORED, None, CircuitOutcome.IGNORED),
        (401, HealthDisposition.FAILURE, HealthFailure.AUTH, CircuitOutcome.IGNORED),
        (403, HealthDisposition.FAILURE, HealthFailure.AUTH, CircuitOutcome.IGNORED),
        (404, HealthDisposition.IGNORED, None, CircuitOutcome.IGNORED),
        (408, HealthDisposition.FAILURE, HealthFailure.TIMEOUT, CircuitOutcome.SAMPLED_FAILURE),
        (425, HealthDisposition.IGNORED, None, CircuitOutcome.THROTTLED),
        (429, HealthDisposition.IGNORED, None, CircuitOutcome.THROTTLED),
        (500, HealthDisposition.FAILURE, HealthFailure.SERVER, CircuitOutcome.SAMPLED_FAILURE),
        (503, HealthDisposition.FAILURE, HealthFailure.SERVER, CircuitOutcome.SAMPLED_FAILURE),
        (600, HealthDisposition.IGNORED, None, CircuitOutcome.IGNORED),
    ],
)
def test_invalid_response_classification(
    status_code: int,
    health_disposition: HealthDisposition,
    health_failure: HealthFailure | None,
    circuit_outcome: CircuitOutcome,
) -> None:
    health = classify_response_failure(status_code)

    assert health.disposition is health_disposition
    assert health.failure is health_failure
    assert classify_response_observation(status_code).outcome is circuit_outcome


@pytest.mark.parametrize(
    ('status_code', 'policy', 'invalid_protocol', 'expected'),
    [
        (401, JsonRpcRetryPolicy.SAFE_ONLY, True, True),
        (403, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
        (200, JsonRpcRetryPolicy.SAFE_ONLY, True, False),
        (200, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
        (400, JsonRpcRetryPolicy.SAFE_ONLY, True, False),
        (400, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
        (408, JsonRpcRetryPolicy.SAFE_ONLY, True, False),
        (408, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
        (425, JsonRpcRetryPolicy.SAFE_ONLY, True, False),
        (425, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
        (429, JsonRpcRetryPolicy.SAFE_ONLY, True, False),
        (429, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
        (500, JsonRpcRetryPolicy.SAFE_ONLY, True, False),
        (500, JsonRpcRetryPolicy.IDEMPOTENT, True, True),
    ],
)
def test_invalid_response_retry_policy(
    status_code: int,
    policy: JsonRpcRetryPolicy,
    invalid_protocol: bool,
    expected: bool,
) -> None:
    assert can_retry_response(status_code, policy, invalid_protocol=invalid_protocol) is expected
