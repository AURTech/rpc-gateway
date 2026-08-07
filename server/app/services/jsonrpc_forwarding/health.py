from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.model.endpoint import EndpointAccessFailureCode, EndpointDescriptor
from app.model.runtime_state.endpoint.health import HealthFailure, HealthObservation, HealthOrigin
from app.services.runtime_state.endpoint.health import HealthDispatcher

_ACCESS_FAILURES: dict[EndpointAccessFailureCode, HealthFailure] = {
    EndpointAccessFailureCode.NOT_FOUND: HealthFailure.CONFIG,
    EndpointAccessFailureCode.DISABLED: HealthFailure.CONFIG,
    EndpointAccessFailureCode.PROTOCOL_MISMATCH: HealthFailure.PROTOCOL,
    EndpointAccessFailureCode.CONFIG_UNAVAILABLE: HealthFailure.CONFIG,
    EndpointAccessFailureCode.TARGET_REJECTED: HealthFailure.CONFIG,
    EndpointAccessFailureCode.INVALID_REQUEST: HealthFailure.PROTOCOL,
    EndpointAccessFailureCode.CONNECTION_FAILED: HealthFailure.CONNECTION,
    EndpointAccessFailureCode.RESPONSE_FAILED: HealthFailure.PROTOCOL,
    EndpointAccessFailureCode.TIMEOUT: HealthFailure.TIMEOUT,
    EndpointAccessFailureCode.RESPONSE_TOO_LARGE: HealthFailure.PROTOCOL,
}


class HealthDisposition(StrEnum):
    SUCCESS = 'success'
    FAILURE = 'failure'
    IGNORED = 'ignored'


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthClassification:
    disposition: HealthDisposition
    failure: HealthFailure | None = None


HEALTH_SUCCESS = HealthClassification(disposition=HealthDisposition.SUCCESS)
HEALTH_IGNORED = HealthClassification(disposition=HealthDisposition.IGNORED)


def classify_access_failure(code: EndpointAccessFailureCode) -> HealthClassification:
    return HealthClassification(disposition=HealthDisposition.FAILURE, failure=_ACCESS_FAILURES[code])


def classify_response_failure(status_code: int) -> HealthClassification:
    if status_code in (401, 403):
        failure = HealthFailure.AUTH
    elif status_code == 408:
        failure = HealthFailure.TIMEOUT
    elif status_code in (425, 429):
        return HEALTH_IGNORED
    elif 500 <= status_code < 600:
        failure = HealthFailure.SERVER
    elif 200 <= status_code < 300:
        failure = HealthFailure.PROTOCOL
    else:
        return HEALTH_IGNORED
    return HealthClassification(disposition=HealthDisposition.FAILURE, failure=failure)


def submit_health(
    dispatcher: HealthDispatcher,
    endpoint: EndpointDescriptor,
    *,
    latency_ms: float,
    classification: HealthClassification,
) -> None:
    if classification.disposition is HealthDisposition.IGNORED:
        return
    observation = HealthObservation(
        endpoint_id=endpoint.id,
        endpoint_version=endpoint.version,
        origin=HealthOrigin.TRAFFIC,
        success=classification.disposition is HealthDisposition.SUCCESS,
        failure=classification.failure,
        latency_ms=latency_ms,
        observed_at=datetime.now(UTC),
    )
    dispatcher.submit(observation)
