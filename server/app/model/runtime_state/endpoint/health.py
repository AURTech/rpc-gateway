from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthStatus(StrEnum):
    UNKNOWN = 'unknown'
    HEALTHY = 'healthy'
    UNHEALTHY = 'unhealthy'


class HealthOrigin(StrEnum):
    TRAFFIC = 'traffic'
    MANUAL = 'manual'


class HealthFailure(StrEnum):
    CONNECTION = 'connection'
    TIMEOUT = 'timeout'
    AUTH = 'auth'
    SERVER = 'server'
    PROTOCOL = 'protocol'
    CONFIG = 'config'


class HealthObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint_id: str = Field(min_length=1, max_length=64)
    endpoint_version: int = Field(ge=1, strict=True)
    origin: HealthOrigin
    success: bool = Field(strict=True)
    failure: HealthFailure | None = None
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_at: datetime

    @field_validator('observed_at')
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Health observation time must include a timezone.')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def validate_outcome(self) -> Self:
        if self.success:
            if self.failure is not None:
                raise ValueError('Successful health observations cannot include a failure.')
            if self.latency_ms is None:
                raise ValueError('Successful health observations must include latency.')
        elif self.failure is None:
            raise ValueError('Failed health observations must include a failure.')
        return self


class EndpointHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    error_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    samples: int = Field(ge=0, strict=True)
    last_observed_at: datetime
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_failure: HealthFailure | None = None

    @field_validator('last_observed_at', 'last_success_at', 'last_failure_at')
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Endpoint health timestamps must include a timezone.')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def validate_failure(self) -> Self:
        if (self.last_failure_at is None) != (self.last_failure is None):
            raise ValueError('Endpoint health failure time and type must be provided together.')
        return self
