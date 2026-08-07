from app.model.endpoint import EndpointAccessFailureCode
from app.model.runtime_state.circuit import (
    CircuitObservation,
    CircuitOutcome,
    CircuitWorkloadClass,
)
from app.services.endpoint.retry_after import parse_retry_after_seconds


def classify_workload(method: str, trace_method_prefixes: tuple[str, ...]) -> CircuitWorkloadClass:
    return (
        CircuitWorkloadClass.TRACE
        if any(method.startswith(prefix) for prefix in trace_method_prefixes)
        else CircuitWorkloadClass.STANDARD
    )


def classify_access_observation(
    code: EndpointAccessFailureCode,
    workload_class: CircuitWorkloadClass,
) -> CircuitObservation:
    if code in {EndpointAccessFailureCode.CONNECTION_FAILED, EndpointAccessFailureCode.RESPONSE_FAILED}:
        outcome = CircuitOutcome.HARD_FAILURE
    elif code is EndpointAccessFailureCode.TIMEOUT:
        outcome = (
            CircuitOutcome.SAMPLED_FAILURE if workload_class is CircuitWorkloadClass.TRACE else CircuitOutcome.HARD_FAILURE
        )
    elif code is EndpointAccessFailureCode.RESPONSE_TOO_LARGE:
        outcome = CircuitOutcome.IGNORED
    else:
        outcome = CircuitOutcome.IGNORED
    return CircuitObservation(outcome=outcome)


def classify_response_observation(
    status_code: int,
    headers: tuple[tuple[str, str], ...] = (),
) -> CircuitObservation:
    if status_code in {425, 429}:
        return CircuitObservation(
            outcome=CircuitOutcome.THROTTLED,
            retry_after_seconds=parse_retry_after_seconds(headers),
        )
    if status_code == 408 or 500 <= status_code < 600 or 200 <= status_code < 300:
        return CircuitObservation(outcome=CircuitOutcome.SAMPLED_FAILURE)
    return CircuitObservation(outcome=CircuitOutcome.IGNORED)
