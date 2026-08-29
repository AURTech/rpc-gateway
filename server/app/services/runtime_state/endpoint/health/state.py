from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.model.runtime_state.endpoint.health import EndpointHealth, HealthFailure, HealthObservation, HealthOrigin, HealthStatus

HEALTH_BUCKET_SECONDS: Final[int] = 10
HEALTH_WINDOW_SECONDS: Final[int] = 60

type HealthBatchKey = tuple[str, int, int]
type HealthWriter = Callable[['HealthBatch'], Awaitable[EndpointHealth]]


@dataclass(frozen=True, slots=True, kw_only=True)
class WindowStats:
    samples: int
    successes: int
    failures: int
    success_latency_micros: int


@dataclass(slots=True, kw_only=True)
class HealthBatch:
    endpoint_id: str
    endpoint_version: int
    bucket_epoch: int
    samples: int
    successes: int
    failures: int
    success_latency_micros: int
    last_observed_at: datetime
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure: HealthFailure | None
    status_override: HealthStatus | None


def bucket_epoch(value: datetime) -> int:
    epoch = int(value.timestamp())
    return epoch - (epoch % HEALTH_BUCKET_SECONDS)


def batch_key(observation: HealthObservation) -> HealthBatchKey:
    return observation.endpoint_id, observation.endpoint_version, bucket_epoch(observation.observed_at)


def make_batch(observation: HealthObservation) -> HealthBatch:
    latency_micros = round(observation.latency_ms * 1000) if observation.success and observation.latency_ms is not None else 0
    status_override = None
    if observation.origin is HealthOrigin.MANUAL:
        status_override = HealthStatus.HEALTHY if observation.success else HealthStatus.UNHEALTHY
    return HealthBatch(
        endpoint_id=observation.endpoint_id,
        endpoint_version=observation.endpoint_version,
        bucket_epoch=bucket_epoch(observation.observed_at),
        samples=1,
        successes=int(observation.success),
        failures=int(not observation.success),
        success_latency_micros=latency_micros,
        last_observed_at=observation.observed_at,
        last_success_at=observation.observed_at if observation.success else None,
        last_failure_at=observation.observed_at if not observation.success else None,
        last_failure=observation.failure,
        status_override=status_override,
    )


def merge_batch(batch: HealthBatch, observation: HealthObservation) -> None:
    if observation.observed_at >= batch.last_observed_at:
        batch.status_override = None
        if observation.origin is HealthOrigin.MANUAL:
            batch.status_override = HealthStatus.HEALTHY if observation.success else HealthStatus.UNHEALTHY
    batch.samples += 1
    if observation.success:
        batch.successes += 1
        if observation.latency_ms is not None:
            batch.success_latency_micros += round(observation.latency_ms * 1000)
        if batch.last_success_at is None or observation.observed_at > batch.last_success_at:
            batch.last_success_at = observation.observed_at
    else:
        batch.failures += 1
        if batch.last_failure_at is None or observation.observed_at > batch.last_failure_at:
            batch.last_failure_at = observation.observed_at
            batch.last_failure = observation.failure
    if observation.observed_at > batch.last_observed_at:
        batch.last_observed_at = observation.observed_at


def select_status(previous: HealthStatus, stats: WindowStats) -> HealthStatus:
    error_rate = stats.failures / stats.samples if stats.samples else 0
    unhealthy = stats.failures >= 3 and (stats.successes == 0 or (stats.samples >= 5 and error_rate >= 0.5))
    if unhealthy:
        return HealthStatus.UNHEALTHY
    recovered = stats.successes >= 3 and (stats.failures == 0 or error_rate <= 0.2)
    if previous is HealthStatus.UNHEALTHY:
        return HealthStatus.HEALTHY if recovered else HealthStatus.UNHEALTHY
    if previous is HealthStatus.UNKNOWN and stats.successes > 0:
        return HealthStatus.HEALTHY
    return previous


def _merge_timestamp(saved: datetime | None, added: datetime | None) -> datetime | None:
    if saved is None:
        return added
    if added is None:
        return saved
    return max(saved, added)


def build_health(batch: HealthBatch, stats: WindowStats, saved: EndpointHealth | None) -> EndpointHealth:
    previous = saved.status if saved is not None else HealthStatus.UNKNOWN
    error_rate = stats.failures / stats.samples if stats.samples else 0
    latency_ms = stats.success_latency_micros / stats.successes / 1000 if stats.successes else None
    last_success_at = _merge_timestamp(saved.last_success_at if saved is not None else None, batch.last_success_at)
    saved_failure_at = saved.last_failure_at if saved is not None else None
    if saved_failure_at is not None and (batch.last_failure_at is None or saved_failure_at > batch.last_failure_at):
        last_failure_at = saved_failure_at
        last_failure = saved.last_failure if saved is not None else None
    else:
        last_failure_at = batch.last_failure_at
        last_failure = batch.last_failure
    status = batch.status_override if batch.status_override is not None else select_status(previous, stats)
    return EndpointHealth(
        status=status,
        error_rate=error_rate,
        latency_ms=latency_ms,
        samples=stats.samples,
        last_observed_at=batch.last_observed_at,
        last_success_at=last_success_at,
        last_failure_at=last_failure_at,
        last_failure=last_failure,
    )


def with_window(health: EndpointHealth, stats: WindowStats, *, keep_status: bool = False) -> EndpointHealth:
    error_rate = stats.failures / stats.samples if stats.samples else 0
    latency_ms = stats.success_latency_micros / stats.successes / 1000 if stats.successes else None
    status = health.status if keep_status else select_status(health.status, stats)
    return health.model_copy(
        update={
            'status': status,
            'error_rate': error_rate,
            'latency_ms': latency_ms,
            'samples': stats.samples,
        }
    )
