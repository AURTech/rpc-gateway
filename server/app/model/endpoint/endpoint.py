from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.model.blockchain import Chain, Network, validate_chain_network
from app.model.endpoint.health import EndpointHealthItem
from app.model.http_auth import PATH_API_KEY_PLACEHOLDER, validate_auth_header_name, validate_auth_query_param
from app.model.provider_state import ProviderEndpointSyncStatus, ProviderVendor


class EndpointOriginType(StrEnum):
    MANUAL = 'manual'
    PROVIDER = 'provider'


class EndpointProtocol(StrEnum):
    JSONRPC = 'jsonrpc'
    HTTP_API = 'http_api'


class EndpointAuthType(StrEnum):
    NONE = 'none'
    BEARER = 'bearer'
    HEADER_API_KEY = 'header_api_key'
    QUERY_API_KEY = 'query_api_key'
    PATH_API_KEY = 'path_api_key'


class EndpointAuditAction(StrEnum):
    CREATED = 'created'
    UPDATED = 'updated'
    DELETED = 'deleted'
    ARCHIVED = 'archived'
    RESTORED = 'restored'


def normalize_endpoint_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError('Endpoint name cannot be empty.')
    return name


def validate_endpoint_url(value: str) -> str:
    url = value.strip()
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.netloc:
        raise ValueError('Endpoint URL must use http:// or https://.')
    return url


def validate_endpoint_auth_url(url: str, auth_type: EndpointAuthType) -> None:
    parts = urlsplit(url)
    segments = parts.path.split('/')
    placeholder_count = segments.count(PATH_API_KEY_PLACEHOLDER)
    misplaced = (
        PATH_API_KEY_PLACEHOLDER in parts.netloc
        or PATH_API_KEY_PLACEHOLDER in parts.query
        or PATH_API_KEY_PLACEHOLDER in parts.fragment
        or any(PATH_API_KEY_PLACEHOLDER in segment and segment != PATH_API_KEY_PLACEHOLDER for segment in segments)
    )
    if misplaced or placeholder_count > 1:
        raise ValueError('Endpoint path auth placeholder is invalid.')
    if placeholder_count and auth_type is not EndpointAuthType.PATH_API_KEY:
        raise ValueError('Endpoint path auth placeholder requires path API key authentication.')


def _normalize_auth_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError('Endpoint auth metadata cannot be empty.')
    return normalized


def _normalize_auth_secret(value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    secret = value.get_secret_value().strip()
    if not secret:
        raise ValueError('Endpoint auth secret cannot be empty.')
    return SecretStr(secret)


class EndpointNoAuthCreateParams(BaseModel):
    type: Literal[EndpointAuthType.NONE] = EndpointAuthType.NONE


class EndpointBearerAuthCreateParams(BaseModel):
    type: Literal[EndpointAuthType.BEARER] = EndpointAuthType.BEARER
    secret: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator('secret')
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        normalized = _normalize_auth_secret(value)
        if normalized is None:
            raise ValueError('Endpoint auth secret is required.')
        return normalized


class EndpointHeaderAuthCreateParams(EndpointBearerAuthCreateParams):
    type: Literal[EndpointAuthType.HEADER_API_KEY] = EndpointAuthType.HEADER_API_KEY
    header_name: str = Field(min_length=1, max_length=128)

    @field_validator('header_name')
    @classmethod
    def validate_header_name(cls, value: str) -> str:
        normalized = _normalize_auth_name(value)
        if normalized is None:
            raise ValueError('Endpoint auth header name is required.')
        return validate_auth_header_name(normalized)


class EndpointQueryAuthCreateParams(EndpointBearerAuthCreateParams):
    type: Literal[EndpointAuthType.QUERY_API_KEY] = EndpointAuthType.QUERY_API_KEY
    query_param: str = Field(min_length=1, max_length=128)

    @field_validator('query_param')
    @classmethod
    def validate_query_param(cls, value: str) -> str:
        normalized = _normalize_auth_name(value)
        if normalized is None:
            raise ValueError('Endpoint auth query parameter is required.')
        return validate_auth_query_param(normalized)


class EndpointPathAuthCreateParams(EndpointBearerAuthCreateParams):
    type: Literal[EndpointAuthType.PATH_API_KEY] = EndpointAuthType.PATH_API_KEY


EndpointCreateAuthParams = Annotated[
    EndpointNoAuthCreateParams
    | EndpointBearerAuthCreateParams
    | EndpointHeaderAuthCreateParams
    | EndpointQueryAuthCreateParams
    | EndpointPathAuthCreateParams,
    Field(discriminator='type'),
]


class EndpointNoAuthUpdateParams(BaseModel):
    type: Literal[EndpointAuthType.NONE] = EndpointAuthType.NONE


class EndpointBearerAuthUpdateParams(BaseModel):
    type: Literal[EndpointAuthType.BEARER] = EndpointAuthType.BEARER
    secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator('secret')
    @classmethod
    def validate_optional_secret(cls, value: SecretStr | None) -> SecretStr | None:
        return _normalize_auth_secret(value)


class EndpointHeaderAuthUpdateParams(EndpointBearerAuthUpdateParams):
    type: Literal[EndpointAuthType.HEADER_API_KEY] = EndpointAuthType.HEADER_API_KEY
    header_name: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator('header_name')
    @classmethod
    def validate_optional_header_name(cls, value: str | None) -> str | None:
        normalized = _normalize_auth_name(value)
        return validate_auth_header_name(normalized) if normalized is not None else None


class EndpointQueryAuthUpdateParams(EndpointBearerAuthUpdateParams):
    type: Literal[EndpointAuthType.QUERY_API_KEY] = EndpointAuthType.QUERY_API_KEY
    query_param: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator('query_param')
    @classmethod
    def validate_optional_query_param(cls, value: str | None) -> str | None:
        normalized = _normalize_auth_name(value)
        return validate_auth_query_param(normalized) if normalized is not None else None


class EndpointPathAuthUpdateParams(EndpointBearerAuthUpdateParams):
    type: Literal[EndpointAuthType.PATH_API_KEY] = EndpointAuthType.PATH_API_KEY


EndpointUpdateAuthParams = Annotated[
    EndpointNoAuthUpdateParams
    | EndpointBearerAuthUpdateParams
    | EndpointHeaderAuthUpdateParams
    | EndpointQueryAuthUpdateParams
    | EndpointPathAuthUpdateParams,
    Field(discriminator='type'),
]


class EndpointNoAuthPublic(BaseModel):
    type: Literal[EndpointAuthType.NONE] = EndpointAuthType.NONE
    has_secret: Literal[False] = False


class EndpointBearerAuthPublic(BaseModel):
    type: Literal[EndpointAuthType.BEARER] = EndpointAuthType.BEARER
    has_secret: Literal[True] = True


class EndpointHeaderAuthPublic(BaseModel):
    type: Literal[EndpointAuthType.HEADER_API_KEY] = EndpointAuthType.HEADER_API_KEY
    header_name: str
    has_secret: Literal[True] = True


class EndpointQueryAuthPublic(BaseModel):
    type: Literal[EndpointAuthType.QUERY_API_KEY] = EndpointAuthType.QUERY_API_KEY
    query_param: str
    has_secret: Literal[True] = True


class EndpointPathAuthPublic(BaseModel):
    type: Literal[EndpointAuthType.PATH_API_KEY] = EndpointAuthType.PATH_API_KEY
    has_secret: Literal[True] = True


EndpointAuthPublic = Annotated[
    EndpointNoAuthPublic
    | EndpointBearerAuthPublic
    | EndpointHeaderAuthPublic
    | EndpointQueryAuthPublic
    | EndpointPathAuthPublic,
    Field(discriminator='type'),
]


class EndpointBearerAuthDetail(EndpointBearerAuthPublic):
    # RPC dashboards commonly expose credentials to authenticated owners as operational configuration.
    # They remain sensitive: never persist plaintext, log values, or use shared/persistent caches.
    secret: str = Field(min_length=1, max_length=4096)


class EndpointHeaderAuthDetail(EndpointHeaderAuthPublic):
    secret: str = Field(min_length=1, max_length=4096)


class EndpointQueryAuthDetail(EndpointQueryAuthPublic):
    secret: str = Field(min_length=1, max_length=4096)


class EndpointPathAuthDetail(EndpointPathAuthPublic):
    secret: str = Field(min_length=1, max_length=4096)


EndpointAuthDetail = Annotated[
    EndpointNoAuthPublic
    | EndpointBearerAuthDetail
    | EndpointHeaderAuthDetail
    | EndpointQueryAuthDetail
    | EndpointPathAuthDetail,
    Field(discriminator='type'),
]


class EndpointValues(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    chain: Chain
    network: Network
    protocol: EndpointProtocol
    url: str = Field(min_length=1, max_length=4096)
    enabled: bool = True
    auth: EndpointCreateAuthParams = Field(default_factory=EndpointNoAuthCreateParams)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_endpoint_name(value)

    @model_validator(mode='after')
    def validate_endpoint_values(self) -> Self:
        validate_chain_network(self.chain, self.network)
        self.url = validate_endpoint_url(self.url)
        validate_endpoint_auth_url(self.url, self.auth.type)
        return self


class CreateEndpointParams(EndpointValues):
    pass


class UpdateEndpointParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool | None = None
    auth: EndpointUpdateAuthParams | None = None

    @field_validator('name')
    @classmethod
    def validate_optional_name(cls, value: str | None) -> str | None:
        return normalize_endpoint_name(value) if value is not None else None

    @model_validator(mode='after')
    def validate_update_fields(self) -> Self:
        if self.model_fields_set == {'expected_version'}:
            raise ValueError('At least one endpoint field must be updated.')
        null_field_submitted = (
            ('name' in self.model_fields_set and self.name is None)
            or ('url' in self.model_fields_set and self.url is None)
            or ('enabled' in self.model_fields_set and self.enabled is None)
            or ('auth' in self.model_fields_set and self.auth is None)
        )
        if null_field_submitted:
            raise ValueError('Endpoint update fields cannot be null.')
        return self


class EndpointListParams(BaseModel):
    q: str | None = Field(default=None, min_length=1, max_length=320)
    chain: list[Chain] | None = None
    network: list[Network] | None = None
    protocol: EndpointProtocol | None = None
    enabled: bool | None = None
    origin_type: EndpointOriginType | None = None
    provider_id: str | None = Field(default=None, min_length=1, max_length=128)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class EndpointAuditListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class EndpointProviderSummary(BaseModel):
    id: str
    name: str
    vendor: ProviderVendor
    vendor_label: str


class EndpointItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    name: str
    origin_type: EndpointOriginType
    provider: EndpointProviderSummary | None
    provider_external_id: str | None
    provider_sync_status: ProviderEndpointSyncStatus | None
    provider_last_seen_at: datetime | None
    chain: Chain
    network: Network
    protocol: EndpointProtocol
    url: str
    effective_url: str | None = None
    enabled: bool
    auth: EndpointAuthPublic
    health: EndpointHealthItem | None = None
    version: int
    created_at: datetime
    modified_at: datetime

    @model_validator(mode='after')
    def validate_supported_pair(self) -> Self:
        validate_chain_network(self.chain, self.network)
        return self


class EndpointDetail(EndpointItem):
    auth: EndpointAuthDetail | EndpointAuthPublic


def redact_endpoint_detail(value: EndpointDetail) -> EndpointItem:
    auth = value.auth
    if isinstance(auth, EndpointHeaderAuthPublic):
        public_auth: EndpointAuthPublic = EndpointHeaderAuthPublic(header_name=auth.header_name)
    elif isinstance(auth, EndpointQueryAuthPublic):
        public_auth = EndpointQueryAuthPublic(query_param=auth.query_param)
    elif isinstance(auth, EndpointPathAuthPublic):
        public_auth = EndpointPathAuthPublic()
    elif isinstance(auth, EndpointBearerAuthPublic):
        public_auth = EndpointBearerAuthPublic()
    else:
        public_auth = EndpointNoAuthPublic()
    fields = value.model_dump(exclude={'auth', 'effective_url'})
    return EndpointItem(**fields, effective_url=None, auth=public_auth)


class EndpointList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[EndpointItem]


class EndpointDeleteResult(BaseModel):
    id: str
    version: int
    deleted: bool


class BulkDeleteEndpointParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    endpoint_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(min_length=1, max_length=50)

    @field_validator('endpoint_ids')
    @classmethod
    def validate_endpoint_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError('Endpoint ids cannot contain duplicates.')
        return value


class BulkDeleteEndpointResult(BaseModel):
    total: int
    deleted: list[EndpointDeleteResult]


class EndpointAuditEventItem(BaseModel):
    id: str
    endpoint_id: str
    account_id: str
    actor_id: str
    actor_token_id: str | None
    action: EndpointAuditAction
    previous_version: int | None
    new_version: int
    changed_fields: list[str]
    created_at: datetime


class EndpointAuditEventList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[EndpointAuditEventItem]
