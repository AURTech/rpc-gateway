from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, computed_field, field_validator, model_validator

from app.model.blockchain import Chain, Network, validate_chain_network
from app.model.endpoint import EndpointItem
from app.model.provider.capability import provider_networks
from app.model.provider_state import (
    ProviderEndpointAction,
    ProviderEndpointSyncStatus,
    ProviderSyncStatus,
    ProviderVendor,
)


def normalize_provider_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError('Provider name cannot be empty.')
    return name


class ProviderCredentialParams(BaseModel):
    secret: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator('secret')
    @classmethod
    def normalize_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError('Provider credential cannot be empty.')
        if any(character.isspace() for character in secret):
            raise ValueError('Provider credential cannot contain whitespace.')
        return SecretStr(secret)


class ProviderCredentialPublic(BaseModel):
    has_secret: bool


class ProviderCredentialDetail(ProviderCredentialPublic):
    # RPC dashboards commonly expose credentials to authenticated owners as operational configuration.
    # They remain sensitive: never persist plaintext, log values, or use shared/persistent caches.
    secret: str = Field(min_length=1, max_length=4096)


class ProviderNetworkPair(BaseModel):
    chain: Chain
    network: Network

    @model_validator(mode='after')
    def validate_pair(self) -> Self:
        validate_chain_network(self.chain, self.network)
        return self


class ProviderSettingsParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tag_ids: list[int] | None = Field(default=None, max_length=50)
    tag_labels: list[str] | None = Field(default=None, max_length=50)
    project: str | None = Field(default=None, min_length=1, max_length=128)
    organization: str | None = Field(default=None, min_length=1, max_length=128)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=128)
    type: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator('tag_ids')
    @classmethod
    def normalize_tag_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        return list(dict.fromkeys(item for item in value if item > 0))

    @field_validator('tag_labels')
    @classmethod
    def normalize_tag_labels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


def _unique_networks(value: list[ProviderNetworkPair]) -> list[ProviderNetworkPair]:
    pairs: dict[tuple[Chain, Network], ProviderNetworkPair] = {}
    for item in value:
        pairs.setdefault((item.chain, item.network), item)
    return list(pairs.values())


def validate_provider_networks(vendor: ProviderVendor, networks: list[ProviderNetworkPair]) -> None:
    supported = provider_networks(vendor)
    unsupported = [item for item in networks if (item.chain, item.network) not in supported]
    if unsupported:
        raise ValueError(f'{vendor.label} provider sync does not support one or more selected networks.')


class CreateProviderParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1, max_length=128)
    vendor: ProviderVendor
    enabled: bool = True
    sync_enabled: bool = False
    credential: ProviderCredentialParams
    settings: ProviderSettingsParams = Field(default_factory=ProviderSettingsParams)
    only_networks: list[ProviderNetworkPair] = Field(default_factory=list, max_length=50)
    ignore_networks: list[ProviderNetworkPair] = Field(default_factory=list, max_length=50)

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return normalize_provider_name(value)

    @field_validator('only_networks', 'ignore_networks')
    @classmethod
    def normalize_networks(cls, value: list[ProviderNetworkPair]) -> list[ProviderNetworkPair]:
        return _unique_networks(value)

    @model_validator(mode='after')
    def validate_network_filters(self) -> Self:
        if self.only_networks and self.ignore_networks:
            raise ValueError('Provider only_networks and ignore_networks cannot both be set.')
        validate_provider_networks(self.vendor, [*self.only_networks, *self.ignore_networks])
        return self


class UpdateProviderParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    sync_enabled: bool | None = None
    credential: ProviderCredentialParams | None = None
    settings: ProviderSettingsParams | None = None
    only_networks: list[ProviderNetworkPair] | None = Field(default=None, max_length=50)
    ignore_networks: list[ProviderNetworkPair] | None = Field(default=None, max_length=50)

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return normalize_provider_name(value) if value is not None else None

    @field_validator('only_networks', 'ignore_networks')
    @classmethod
    def normalize_networks(cls, value: list[ProviderNetworkPair] | None) -> list[ProviderNetworkPair] | None:
        return _unique_networks(value) if value is not None else None

    @model_validator(mode='after')
    def validate_update(self) -> Self:
        if self.model_fields_set == {'expected_version'}:
            raise ValueError('At least one provider field must be updated.')
        update_values = self.model_dump(include=self.model_fields_set)
        if any(value is None for name, value in update_values.items() if name != 'expected_version'):
            raise ValueError('Provider update fields cannot be null.')
        only = self.only_networks
        ignored = self.ignore_networks
        if only and ignored:
            raise ValueError('Provider only_networks and ignore_networks cannot both be set.')
        return self


class ProviderListParams(BaseModel):
    vendor: list[ProviderVendor] | None = Field(default=None, max_length=20)
    enabled: bool | None = None
    sync_enabled: bool | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class ProviderEndpointListParams(BaseModel):
    sync_status: ProviderEndpointSyncStatus | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class ProviderDeleteParams(BaseModel):
    delete_unreferenced_endpoints: bool = False


class ProviderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    name: str
    vendor: ProviderVendor
    enabled: bool
    sync_enabled: bool
    credential: ProviderCredentialPublic
    settings: dict[str, Any]
    only_networks: list[ProviderNetworkPair]
    ignore_networks: list[ProviderNetworkPair]
    last_sync_at: datetime | None
    last_sync_status: ProviderSyncStatus
    last_sync_error: str | None
    last_sync_created: int
    last_sync_updated: int
    last_sync_restored: int
    last_sync_archived: int
    last_sync_skipped: int
    version: int
    created_at: datetime
    modified_at: datetime

    @computed_field
    @property
    def vendor_label(self) -> str:
        return self.vendor.label


class ProviderDetail(ProviderItem):
    credential: ProviderCredentialDetail


def redact_provider_detail(value: ProviderDetail) -> ProviderItem:
    fields = value.model_dump(exclude={'credential'})
    credential = ProviderCredentialPublic(has_secret=value.credential.has_secret)
    return ProviderItem(**fields, credential=credential)


class ProviderList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[ProviderItem]


class ProviderSyncItem(BaseModel):
    chain: Chain | None = None
    network: Network | None = None
    action: ProviderEndpointAction
    endpoint_id: str | None = None
    external_id: str | None = None
    error: str | None = None


class ProviderSyncResult(BaseModel):
    provider_id: str
    status: ProviderSyncStatus
    created: int
    updated: int
    restored: int
    archived: int
    skipped: int
    route_targets_added: int = 0
    route_targets_removed: int = 0
    route_targets_skipped: int = 0
    items: list[ProviderSyncItem] = Field(default_factory=list)


class ProviderEndpointItem(BaseModel):
    endpoint: EndpointItem
    sync_status: ProviderEndpointSyncStatus
    external_id: str
    last_seen_at: datetime | None
    archived_at: datetime | None


class ProviderEndpointList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[ProviderEndpointItem]


class ProviderDeleteResult(BaseModel):
    id: str
    version: int
    deleted: bool
    archived_endpoints: int = Field(ge=0)
    retained_endpoints: int = Field(ge=0)
    detached_endpoints: int = Field(ge=0)
