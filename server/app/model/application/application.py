from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.model.blockchain import Chain
from app.model.pagination import CreatedAtListParams, ListSort
from app.model.provider_state import ProviderVendor


def normalize_app_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError('App name cannot be empty.')
    return name


class AppKeyState(StrEnum):
    ACTIVE = 'active'
    GRACE = 'grace'
    REVOKED = 'revoked'
    EXPIRED = 'expired'


class AppAuditAction(StrEnum):
    CREATED = 'created'
    UPDATED = 'updated'
    DELETED = 'deleted'
    API_KEY_CREATED = 'api_key_created'
    # Retained so existing audit rows remain readable after removing the reveal endpoint.
    API_KEY_REVEALED = 'api_key_revealed'
    API_KEY_REVOKED = 'api_key_revoked'


class CreateAppParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_app_name(value)


class UpdateAppParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_app_name(value) if value is not None else None

    @model_validator(mode='after')
    def validate_update_fields(self) -> 'UpdateAppParams':
        if self.model_fields_set == {'expected_version'}:
            raise ValueError('At least one App field must be updated.')
        if ('name' in self.model_fields_set and self.name is None) or (
            'enabled' in self.model_fields_set and self.enabled is None
        ):
            raise ValueError('App update fields cannot be null.')
        return self


class AppItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    enabled: bool
    provider_id: str | None = None
    version: int
    created_at: datetime
    modified_at: datetime


class CreatedApp(AppItem):
    api_key_id: str
    api_key: str = Field(min_length=1, max_length=128)


class AppListItem(AppItem):
    chains: list[Chain]
    gateway_count: int
    enabled_gateway_count: int


class AppList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[AppListItem]


class AppListParams(CreatedAtListParams):
    search: str | None = Field(default=None, min_length=1, max_length=320)
    enabled: bool | None = None
    provider_id: str | None = Field(default=None, min_length=1, max_length=64)
    sort: ListSort = 'DESC'


class DeletedApp(BaseModel):
    id: str
    version: int
    deleted: bool


class AppProviderItem(BaseModel):
    id: str
    name: str
    vendor: ProviderVendor

    @computed_field
    @property
    def vendor_label(self) -> str:
        return self.vendor.label


class SetAppProviderParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    provider_id: str = Field(min_length=1, max_length=64)


class AppProviderResult(BaseModel):
    app_id: str
    provider: AppProviderItem | None
    route_targets_added: int = Field(ge=0)
    route_targets_removed: int = Field(ge=0)
    route_targets_skipped: int = Field(ge=0)


class AppKeyItem(BaseModel):
    # RPC dashboards commonly expose credentials to authenticated owners as operational configuration.
    # The value remains sensitive: persist only ciphertext/digests and never log it or use shared/persistent caches.
    id: str
    api_key: str = Field(min_length=1, max_length=128)
    state: AppKeyState
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CreatedAppKey(AppKeyItem):
    pass


class AppKeyList(BaseModel):
    total: int
    items: list[AppKeyItem]
