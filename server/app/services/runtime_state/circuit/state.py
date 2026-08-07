import secrets
from datetime import datetime, timedelta
from typing import Self

from pydantic import Field, model_validator

from app.model.runtime_state.circuit import (
    CircuitDecision,
    CircuitOpenReason,
    CircuitOutcome,
    CircuitPolicy,
    CircuitSnapshot,
    CircuitState,
    CircuitWorkloadClass,
)


class CircuitRecord(CircuitSnapshot):
    probe_token: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def validate_probe(self) -> Self:
        if self.state is CircuitState.HALF_OPEN:
            if (self.probe_token is None) != (self.probe_until is None):
                raise ValueError('Half-open circuit probe token and expiry must be provided together.')
        elif self.probe_token is not None:
            raise ValueError('Only half-open circuit state can include a probe token.')
        return self


def closed_record(
    endpoint_id: str,
    endpoint_version: int,
    workload_class: CircuitWorkloadClass = CircuitWorkloadClass.STANDARD,
) -> CircuitRecord:
    snapshot = CircuitSnapshot(
        endpoint_id=endpoint_id,
        endpoint_version=endpoint_version,
        workload_class=workload_class,
    )
    return CircuitRecord.model_validate(snapshot.model_dump())


def to_snapshot(record: CircuitRecord) -> CircuitSnapshot:
    return CircuitSnapshot.model_validate(record.model_dump(exclude={'probe_token'}))


def make_decision(record: CircuitSnapshot, *, allowed: bool, probe_token: str | None = None) -> CircuitDecision:
    retry_at = record.probe_until if record.state is CircuitState.HALF_OPEN and not allowed else record.retry_at
    return CircuitDecision(
        endpoint_id=record.endpoint_id,
        endpoint_version=record.endpoint_version,
        workload_class=record.workload_class,
        window_generation=record.window_generation,
        allowed=allowed,
        state=record.state,
        failures=record.failures,
        epoch=record.epoch,
        open_reason=record.open_reason,
        probe_token=probe_token,
        retry_at=retry_at,
    )


def next_backoff_step(policy: CircuitPolicy, step: int) -> int:
    return step if open_delay(policy, step) >= policy.max_open_seconds else step + 1


def apply_outcome(
    policy: CircuitPolicy,
    record: CircuitRecord,
    *,
    outcome: CircuitOutcome,
    now: datetime,
    throttle_seconds: int | None = None,
) -> CircuitRecord:
    if record.state is CircuitState.CLOSED:
        if outcome is CircuitOutcome.SUCCESS:
            return _with_record(record, {'failures': 0, 'updated_at': now})
        if outcome in {CircuitOutcome.IGNORED, CircuitOutcome.SAMPLED_FAILURE}:
            return record
        if outcome is CircuitOutcome.THROTTLED:
            return make_open(
                policy,
                record,
                now=now,
                failures=record.failures,
                backoff_step=record.backoff_step,
                reason=CircuitOpenReason.THROTTLED,
                delay_seconds=throttle_seconds,
            )
        failures = record.failures + 1
        if failures >= policy.failure_threshold:
            return make_open(
                policy,
                record,
                now=now,
                failures=failures,
                backoff_step=0,
                reason=CircuitOpenReason.HARD_FAILURE,
            )
        return _with_record(record, {'failures': failures, 'last_failure_at': now, 'updated_at': now})

    if outcome in {CircuitOutcome.HARD_FAILURE, CircuitOutcome.SAMPLED_FAILURE}:
        return make_open(
            policy,
            record,
            now=now,
            failures=max(record.failures, policy.failure_threshold),
            backoff_step=next_backoff_step(policy, record.backoff_step),
            reason=CircuitOpenReason.HARD_FAILURE,
        )
    if outcome is CircuitOutcome.THROTTLED:
        return make_open(
            policy,
            record,
            now=now,
            failures=record.failures,
            backoff_step=record.backoff_step,
            reason=CircuitOpenReason.THROTTLED,
            delay_seconds=throttle_seconds,
        )
    if outcome is CircuitOutcome.IGNORED:
        return _with_record(
            record,
            {'epoch': record.epoch + 1, 'probe_token': None, 'probe_until': None, 'updated_at': now},
        )

    successes = record.probe_successes + 1
    wanted_successes = 1 if record.open_reason is CircuitOpenReason.THROTTLED else policy.recovery_successes
    if successes >= wanted_successes:
        return _with_record(
            record,
            {
                'state': CircuitState.CLOSED,
                'failures': 0,
                'epoch': record.epoch + 1,
                'window_generation': record.window_generation + 1,
                'backoff_step': 0,
                'probe_successes': 0,
                'open_reason': None,
                'opened_at': None,
                'retry_at': None,
                'probe_token': None,
                'probe_until': None,
                'updated_at': now,
            },
        )
    return _with_record(
        record,
        {
            'epoch': record.epoch + 1,
            'probe_successes': successes,
            'probe_token': None,
            'probe_until': None,
            'updated_at': now,
        },
    )


def make_open(
    policy: CircuitPolicy,
    record: CircuitRecord,
    *,
    now: datetime,
    failures: int,
    backoff_step: int,
    reason: CircuitOpenReason,
    delay_seconds: int | None = None,
) -> CircuitRecord:
    delay = delay_seconds if delay_seconds is not None else open_delay(policy, backoff_step)
    return _with_record(
        record,
        {
            'state': CircuitState.OPEN,
            'failures': failures,
            'epoch': record.epoch + 1,
            'window_generation': record.window_generation + 1,
            'backoff_step': backoff_step,
            'probe_successes': 0,
            'open_reason': reason,
            'opened_at': now,
            'retry_at': now + timedelta(seconds=delay),
            'probe_token': None,
            'probe_until': None,
            'last_failure_at': now,
            'updated_at': now,
        },
    )


def grant_probe(policy: CircuitPolicy, record: CircuitRecord, *, now: datetime, increment_epoch: bool) -> CircuitRecord:
    return _with_record(
        record,
        {
            'state': CircuitState.HALF_OPEN,
            'epoch': record.epoch + 1 if increment_epoch else record.epoch,
            'probe_token': secrets.token_urlsafe(16),
            'probe_until': now + timedelta(seconds=policy.probe_seconds),
            'updated_at': now,
        },
    )


def _with_record(record: CircuitRecord, changes: dict[str, object]) -> CircuitRecord:
    values = record.model_dump()
    values.update(changes)
    return CircuitRecord.model_validate(values)


def open_delay(policy: CircuitPolicy, step: int) -> int:
    return min(policy.open_seconds * 2 ** min(step, 16), policy.max_open_seconds)
