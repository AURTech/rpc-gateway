from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.model.admission import AdmissionMode, AdmissionRuntimePolicy
from app.model.pagination import DEFAULT_LIST_PAGE_SIZE, MAX_LIST_PAGE_SIZE


class JsonRpcRateLimitBucket(BaseModel):
    model_config = ConfigDict(frozen=True)

    rps: int = Field(ge=1, le=1_000_000)
    burst: int = Field(ge=1, le=10_000_000)


class JsonRpcRateLimitPolicyItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: AdmissionMode = Field(
        description='Controls request-per-second limits; the per-process simultaneous request limit is always enforced.'
    )
    max_inflight_per_worker: int = Field(
        ge=1,
        le=100_000,
        description='Maximum simultaneous JSON-RPC requests handled by one API process.',
    )
    redis_timeout_ms: int = Field(ge=1, le=5000)
    redis_admission_per_worker: int = Field(ge=1, le=100_000)
    fallback_max_keys_per_worker: int = Field(ge=1000, le=10_000_000)
    global_limit: JsonRpcRateLimitBucket
    ip_limit: JsonRpcRateLimitBucket
    account_limit: JsonRpcRateLimitBucket
    app_limit: JsonRpcRateLimitBucket
    version: int = Field(ge=1)
    modified_by_account_id: str | None
    created_at: datetime
    modified_at: datetime

    def to_runtime_policy(self) -> AdmissionRuntimePolicy:
        return AdmissionRuntimePolicy(
            mode=self.mode,
            version=self.version,
            redis_timeout_ms=self.redis_timeout_ms,
            redis_admission_per_worker=self.redis_admission_per_worker,
            fallback_max_keys_per_worker=self.fallback_max_keys_per_worker,
        )


class UpdateJsonRpcRateLimitPolicyParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    expected_version: int = Field(ge=1)
    mode: AdmissionMode | None = None
    max_inflight_per_worker: int | None = Field(
        default=None,
        ge=1,
        le=100_000,
    )
    redis_timeout_ms: int | None = Field(default=None, ge=1, le=5000)
    redis_admission_per_worker: int | None = Field(default=None, ge=1, le=100_000)
    fallback_max_keys_per_worker: int | None = Field(default=None, ge=1000, le=10_000_000)
    global_limit: JsonRpcRateLimitBucket | None = None
    ip_limit: JsonRpcRateLimitBucket | None = None
    account_limit: JsonRpcRateLimitBucket | None = None
    app_limit: JsonRpcRateLimitBucket | None = None

    @model_validator(mode='after')
    def validate_update_fields(self) -> Self:
        if self.model_fields_set == {'expected_version'}:
            raise ValueError('At least one rate limit policy field must be updated.')
        update_values = self.model_dump(exclude={'expected_version'}, exclude_unset=True)
        if any(value is None for value in update_values.values()):
            raise ValueError('Rate limit policy fields cannot be null.')
        return self


class JsonRpcRateLimitAuditListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=DEFAULT_LIST_PAGE_SIZE, ge=1, le=MAX_LIST_PAGE_SIZE)


class JsonRpcRateLimitAuditEventItem(BaseModel):
    id: str
    actor_id: str
    actor_token_id: str | None
    previous_version: int
    new_version: int
    changed_fields: list[str]
    created_at: datetime


class JsonRpcRateLimitAuditEventList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[JsonRpcRateLimitAuditEventItem]
