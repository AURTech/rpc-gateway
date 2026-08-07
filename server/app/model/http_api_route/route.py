from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.model.endpoint import EndpointTrustLevel


class HttpApiRoutingStrategyType(StrEnum):
    LOAD_BALANCE = 'load_balance'
    PRIORITY_FAILOVER = 'priority_failover'


class HttpApiRetryPolicy(StrEnum):
    SAFE_ONLY = 'safe_only'
    IDEMPOTENT = 'idempotent'


class HttpApiLoadBalanceTargetParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    endpoint_id: str = Field(min_length=1, max_length=64)
    weight: int = Field(default=100, ge=1, le=1000, strict=True)


class HttpApiLoadBalanceParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: Literal[HttpApiRoutingStrategyType.LOAD_BALANCE] = HttpApiRoutingStrategyType.LOAD_BALANCE
    targets: list[HttpApiLoadBalanceTargetParams] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def validate_targets(self) -> Self:
        endpoint_ids = [target.endpoint_id for target in self.targets]
        if len(endpoint_ids) != len(set(endpoint_ids)):
            raise ValueError('HTTP API route target Endpoint ids cannot contain duplicates.')
        return self


class HttpApiPriorityFailoverTargetParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    endpoint_id: str = Field(min_length=1, max_length=64)


class HttpApiPriorityFailoverParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: Literal[HttpApiRoutingStrategyType.PRIORITY_FAILOVER] = HttpApiRoutingStrategyType.PRIORITY_FAILOVER
    targets: list[HttpApiPriorityFailoverTargetParams] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def validate_targets(self) -> Self:
        endpoint_ids = [target.endpoint_id for target in self.targets]
        if len(endpoint_ids) != len(set(endpoint_ids)):
            raise ValueError('HTTP API route target Endpoint ids cannot contain duplicates.')
        return self


HttpApiRoutingStrategyParams = Annotated[
    HttpApiLoadBalanceParams | HttpApiPriorityFailoverParams,
    Field(discriminator='type'),
]


class HttpApiRouteValues(BaseModel):
    model_config = ConfigDict(extra='forbid')

    minimum_trust: EndpointTrustLevel = EndpointTrustLevel.UNVERIFIED
    max_latency_ms: float | None = Field(default=None, gt=0, le=120_000, allow_inf_nan=False)
    max_attempts: int = Field(default=3, ge=1, le=10, strict=True)
    retry_policy: HttpApiRetryPolicy = HttpApiRetryPolicy.SAFE_ONLY
    strategy: HttpApiRoutingStrategyParams


class ReplaceHttpApiRouteParams(HttpApiRouteValues):
    expected_version: int = Field(ge=1, strict=True)


class HttpApiLoadBalanceTargetItem(BaseModel):
    endpoint_id: str
    position: int
    weight: int


class HttpApiLoadBalanceItem(BaseModel):
    type: Literal[HttpApiRoutingStrategyType.LOAD_BALANCE] = HttpApiRoutingStrategyType.LOAD_BALANCE
    targets: list[HttpApiLoadBalanceTargetItem]


class HttpApiPriorityFailoverTargetItem(BaseModel):
    endpoint_id: str
    position: int


class HttpApiPriorityFailoverItem(BaseModel):
    type: Literal[HttpApiRoutingStrategyType.PRIORITY_FAILOVER] = HttpApiRoutingStrategyType.PRIORITY_FAILOVER
    targets: list[HttpApiPriorityFailoverTargetItem]


HttpApiRoutingStrategyItem = Annotated[
    HttpApiLoadBalanceItem | HttpApiPriorityFailoverItem,
    Field(discriminator='type'),
]


class HttpApiRouteItem(BaseModel):
    id: str
    gateway_id: str
    minimum_trust: EndpointTrustLevel
    max_latency_ms: float | None
    max_attempts: int
    retry_policy: HttpApiRetryPolicy
    strategy: HttpApiRoutingStrategyItem
    version: int
    created_at: datetime
    modified_at: datetime
