from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.model.blockchain import Chain, Network
from app.model.pagination import CreatedAtListParams, ListSort
from app.model.transport import Transport


def normalize_gateway_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError('Gateway name cannot be empty.')
    return name


class UpdateGatewayParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_gateway_name(value) if value is not None else None

    @model_validator(mode='after')
    def validate_update_fields(self) -> 'UpdateGatewayParams':
        if self.model_fields_set == {'expected_version'}:
            raise ValueError('At least one Gateway field must be updated.')
        if ('name' in self.model_fields_set and self.name is None) or (
            'enabled' in self.model_fields_set and self.enabled is None
        ):
            raise ValueError('Gateway update fields cannot be null.')
        return self


class GatewayBulkTargetParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)


class BulkUpdateGatewayParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool
    gateways: list[GatewayBulkTargetParams] = Field(min_length=1, max_length=50)

    @field_validator('gateways')
    @classmethod
    def validate_gateways(cls, value: list[GatewayBulkTargetParams]) -> list[GatewayBulkTargetParams]:
        gateway_ids = [target.id for target in value]
        if len(gateway_ids) != len(set(gateway_ids)):
            raise ValueError('Gateway ids cannot contain duplicates.')
        return value


class GatewayAccessPoint(BaseModel):
    transport: Transport
    url: str


class GatewayItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    app_id: str
    app_name: str
    name: str
    chain: Chain
    network: Network
    enabled: bool
    effective_enabled: bool
    version: int
    access_points: list[GatewayAccessPoint]
    created_at: datetime
    modified_at: datetime


class GatewayList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[GatewayItem]


class BulkUpdateGatewayResult(BaseModel):
    total: int
    items: list[GatewayItem]


class GatewayListParams(CreatedAtListParams):
    search: str | None = Field(default=None, min_length=1, max_length=320)
    app_id: str | None = Field(default=None, min_length=1, max_length=128)
    chain: list[Chain] | None = Field(default=None, max_length=20)
    network: list[Network] | None = Field(default=None, max_length=20)
    enabled: bool | None = None
    sort: ListSort = 'DESC'
