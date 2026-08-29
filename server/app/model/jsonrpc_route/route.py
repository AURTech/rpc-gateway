from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class JsonRpcRoutingStrategyType(StrEnum):
    LOAD_BALANCE = 'load_balance'
    PRIORITY_FAILOVER = 'priority_failover'


class JsonRpcRetryPolicy(StrEnum):
    SAFE_ONLY = 'safe_only'
    IDEMPOTENT = 'idempotent'


class JsonRpcLoadBalanceTargetParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    endpoint_id: str = Field(min_length=1, max_length=64)
    weight: int = Field(default=100, ge=1, le=1000, strict=True)


class JsonRpcLoadBalanceParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: Literal[JsonRpcRoutingStrategyType.LOAD_BALANCE] = JsonRpcRoutingStrategyType.LOAD_BALANCE
    targets: list[JsonRpcLoadBalanceTargetParams] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def validate_targets(self) -> Self:
        endpoint_ids = [target.endpoint_id for target in self.targets]
        if len(endpoint_ids) != len(set(endpoint_ids)):
            raise ValueError('JSON-RPC route target Endpoint ids cannot contain duplicates.')
        return self


class JsonRpcPriorityFailoverTargetParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    endpoint_id: str = Field(min_length=1, max_length=64)


class JsonRpcPriorityFailoverParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: Literal[JsonRpcRoutingStrategyType.PRIORITY_FAILOVER] = JsonRpcRoutingStrategyType.PRIORITY_FAILOVER
    targets: list[JsonRpcPriorityFailoverTargetParams] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def validate_targets(self) -> Self:
        endpoint_ids = [target.endpoint_id for target in self.targets]
        if len(endpoint_ids) != len(set(endpoint_ids)):
            raise ValueError('JSON-RPC route target Endpoint ids cannot contain duplicates.')
        return self


JsonRpcRoutingStrategyParams = Annotated[
    JsonRpcLoadBalanceParams | JsonRpcPriorityFailoverParams,
    Field(discriminator='type'),
]


class JsonRpcRouteValues(BaseModel):
    model_config = ConfigDict(extra='forbid')

    max_attempts: int = Field(default=3, ge=1, le=10, strict=True)
    retry_policy: JsonRpcRetryPolicy = JsonRpcRetryPolicy.SAFE_ONLY
    strategy: JsonRpcRoutingStrategyParams


class ReplaceJsonRpcRouteParams(JsonRpcRouteValues):
    expected_version: int = Field(ge=1, strict=True)


class CreateJsonRpcMethodRouteParams(JsonRpcRouteValues):
    methods: list[str] = Field(min_length=1, max_length=100)

    @field_validator('methods')
    @classmethod
    def validate_methods(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 256 for value in values):
            raise ValueError('JSON-RPC route methods must contain between 1 and 256 characters.')
        if len(values) != len(set(values)):
            raise ValueError('JSON-RPC route methods cannot contain duplicates.')
        return values


class ReplaceJsonRpcMethodRouteParams(CreateJsonRpcMethodRouteParams):
    expected_version: int = Field(ge=1, strict=True)


class DeleteJsonRpcMethodRouteParams(BaseModel):
    expected_version: int = Field(ge=1)


class JsonRpcLoadBalanceTargetItem(BaseModel):
    endpoint_id: str
    position: int
    weight: int


class JsonRpcLoadBalanceItem(BaseModel):
    type: Literal[JsonRpcRoutingStrategyType.LOAD_BALANCE] = JsonRpcRoutingStrategyType.LOAD_BALANCE
    targets: list[JsonRpcLoadBalanceTargetItem]


class JsonRpcPriorityFailoverTargetItem(BaseModel):
    endpoint_id: str
    position: int


class JsonRpcPriorityFailoverItem(BaseModel):
    type: Literal[JsonRpcRoutingStrategyType.PRIORITY_FAILOVER] = JsonRpcRoutingStrategyType.PRIORITY_FAILOVER
    targets: list[JsonRpcPriorityFailoverTargetItem]


JsonRpcRoutingStrategyItem = Annotated[
    JsonRpcLoadBalanceItem | JsonRpcPriorityFailoverItem,
    Field(discriminator='type'),
]


class JsonRpcRouteItem(BaseModel):
    id: str
    gateway_id: str
    methods: list[str]
    is_default: bool
    max_attempts: int
    retry_policy: JsonRpcRetryPolicy
    strategy: JsonRpcRoutingStrategyItem
    version: int
    created_at: datetime
    modified_at: datetime


class JsonRpcMethodRouteList(BaseModel):
    total: int
    items: list[JsonRpcRouteItem]
