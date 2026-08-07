from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CircuitState(StrEnum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class CircuitWorkloadClass(StrEnum):
    STANDARD = 'standard'
    TRACE = 'trace'


class CircuitOpenReason(StrEnum):
    HARD_FAILURE = 'hard_failure'
    ERROR_RATE = 'error_rate'
    THROTTLED = 'throttled'


class CircuitOutcome(StrEnum):
    SUCCESS = 'success'
    HARD_FAILURE = 'hard_failure'
    SAMPLED_FAILURE = 'sampled_failure'
    THROTTLED = 'throttled'
    IGNORED = 'ignored'


class CircuitObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: CircuitOutcome
    retry_after_seconds: int | None = Field(default=None, ge=1, le=3600, strict=True)

    @model_validator(mode='after')
    def validate_retry_after(self) -> Self:
        if self.outcome is not CircuitOutcome.THROTTLED and self.retry_after_seconds is not None:
            raise ValueError('Only throttled Circuit observations can include Retry-After.')
        return self


class CircuitPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    failure_threshold: int = Field(default=5, ge=3, le=100, strict=True)
    window_seconds: int = Field(default=30, ge=10, le=300, strict=True)
    window_bucket_seconds: int = Field(default=5, ge=1, le=60, strict=True)
    window_min_samples: int = Field(default=20, ge=5, le=100_000, strict=True)
    window_failure_rate: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)
    open_seconds: int = Field(default=30, ge=1, le=300, strict=True)
    recovery_successes: int = Field(default=2, ge=1, le=5, strict=True)
    probe_seconds: int = Field(default=30, ge=1, le=300, strict=True)
    max_open_seconds: int = Field(default=300, ge=1, le=3600, strict=True)
    throttle_seconds: int = Field(default=2, ge=1, le=300, strict=True)
    throttle_max_seconds: int = Field(default=30, ge=1, le=600, strict=True)
    cache_ttl_ms: int = Field(default=100, ge=0, le=1000, strict=True)
    cache_max_items: int = Field(default=10_000, ge=100, le=1_000_000, strict=True)
    operation_timeout_ms: int = Field(default=200, ge=10, le=2000, strict=True)
    state_ttl_seconds: int = Field(default=24 * 60 * 60, ge=60, le=7 * 24 * 60 * 60, strict=True)

    @model_validator(mode='after')
    def validate_durations(self) -> Self:
        if self.window_seconds % self.window_bucket_seconds:
            raise ValueError('Circuit window must be exactly divisible by its bucket duration.')
        if self.max_open_seconds < self.open_seconds:
            raise ValueError('Circuit maximum open time cannot be shorter than its initial open time.')
        if self.throttle_max_seconds < self.throttle_seconds:
            raise ValueError('Circuit throttle maximum cannot be shorter than its default.')
        if self.state_ttl_seconds < max(self.max_open_seconds, self.throttle_max_seconds) + self.probe_seconds:
            raise ValueError('Circuit state TTL must cover the maximum open and probe times.')
        return self


class CircuitSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_id: str = Field(min_length=1, max_length=64)
    endpoint_version: int = Field(ge=1, strict=True)
    workload_class: CircuitWorkloadClass = CircuitWorkloadClass.STANDARD
    state: CircuitState = CircuitState.CLOSED
    failures: int = Field(default=0, ge=0, strict=True)
    epoch: int = Field(default=0, ge=0, strict=True)
    window_generation: int = Field(default=0, ge=0, strict=True)
    backoff_step: int = Field(default=0, ge=0, strict=True)
    probe_successes: int = Field(default=0, ge=0, strict=True)
    open_reason: CircuitOpenReason | None = None
    opened_at: datetime | None = None
    retry_at: datetime | None = None
    probe_until: datetime | None = None
    last_failure_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator('opened_at', 'retry_at', 'probe_until', 'last_failure_at', 'updated_at')
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Circuit timestamps must include a timezone.')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def validate_state(self) -> Self:
        if self.state is CircuitState.CLOSED:
            if any(value is not None for value in (self.open_reason, self.opened_at, self.retry_at, self.probe_until)):
                raise ValueError('Closed circuit state cannot retain open or probe metadata.')
            if self.probe_successes != 0 or self.backoff_step != 0:
                raise ValueError('Closed circuit state cannot retain recovery progress.')
        elif self.open_reason is None or self.opened_at is None or self.retry_at is None:
            raise ValueError('Open and half-open circuit states must include reason and retry times.')
        if self.state is CircuitState.OPEN and (self.probe_until is not None or self.probe_successes != 0):
            raise ValueError('Open circuit state cannot retain an active probe.')
        return self


class CircuitDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_id: str = Field(min_length=1, max_length=64)
    endpoint_version: int = Field(ge=1, strict=True)
    workload_class: CircuitWorkloadClass = CircuitWorkloadClass.STANDARD
    window_generation: int = Field(default=0, ge=0, strict=True)
    allowed: bool = Field(strict=True)
    state: CircuitState
    failures: int = Field(ge=0, strict=True)
    epoch: int = Field(ge=0, strict=True)
    open_reason: CircuitOpenReason | None = None
    probe_token: str | None = Field(default=None, min_length=1, max_length=64)
    retry_at: datetime | None = None

    @field_validator('retry_at')
    @classmethod
    def validate_retry_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Circuit retry time must include a timezone.')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def validate_decision(self) -> Self:
        if self.state is CircuitState.CLOSED and not self.allowed:
            raise ValueError('Closed circuit decisions must allow the attempt.')
        if self.state is CircuitState.OPEN and self.allowed:
            raise ValueError('Open circuit decisions cannot allow the attempt.')
        if self.allowed and self.state is CircuitState.HALF_OPEN and self.probe_token is None:
            raise ValueError('Allowed half-open decisions must include a probe token.')
        if (not self.allowed or self.state is not CircuitState.HALF_OPEN) and self.probe_token is not None:
            raise ValueError('Only allowed half-open decisions can include a probe token.')
        return self
