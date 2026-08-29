from enum import StrEnum

from pydantic import BaseModel, Field


class EndpointRouteType(StrEnum):
    JSONRPC_DEFAULT = 'jsonrpc_default'
    JSONRPC_METHOD = 'jsonrpc_method'
    HTTP_API = 'http_api'


class EndpointRouteStrategyType(StrEnum):
    PRIORITY_FAILOVER = 'priority_failover'
    LOAD_BALANCE = 'load_balance'


class EndpointRouteGatewayItem(BaseModel):
    id: str
    app_id: str
    name: str


class EndpointRouteBindingItem(BaseModel):
    route_type: EndpointRouteType
    route_id: str
    route_version: int = Field(ge=1)
    strategy_type: EndpointRouteStrategyType
    methods: list[str]
    target_count: int = Field(ge=1)
    gateway: EndpointRouteGatewayItem


class EndpointRouteBindingList(BaseModel):
    total: int = Field(ge=0)
    items: list[EndpointRouteBindingItem]


class DeleteEndpointRouteBindingParams(BaseModel):
    expected_version: int = Field(ge=1)


class EndpointRouteBindingDeleteResult(BaseModel):
    endpoint_id: str
    route_type: EndpointRouteType
    route_id: str
    route_deleted: bool
    route_version: int | None = Field(default=None, ge=1)
