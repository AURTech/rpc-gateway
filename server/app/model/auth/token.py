from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class PersonalAccessTokenScope(StrEnum):
    OVERVIEW_READ = 'overview:read'
    APPS_READ = 'apps:read'
    APPS_WRITE = 'apps:write'
    APP_KEYS_READ = 'app-keys:read'
    APP_KEYS_WRITE = 'app-keys:write'
    GATEWAYS_READ = 'gateways:read'
    GATEWAYS_WRITE = 'gateways:write'
    ENDPOINTS_READ = 'endpoints:read'
    ENDPOINTS_WRITE = 'endpoints:write'
    ENDPOINT_SECRETS_READ = 'endpoint-secrets:read'
    PROVIDERS_READ = 'providers:read'
    PROVIDERS_WRITE = 'providers:write'
    PROVIDER_SECRETS_READ = 'provider-secrets:read'
    ROUTES_READ = 'routes:read'
    ROUTES_WRITE = 'routes:write'
    USAGE_READ = 'usage:read'
    META_READ = 'meta:read'
    ACCOUNTS_READ = 'accounts:read'
    ACCOUNTS_WRITE = 'accounts:write'
    POLICIES_READ = 'policies:read'
    POLICIES_WRITE = 'policies:write'


ADMIN_PAT_SCOPES = frozenset(
    {
        PersonalAccessTokenScope.ACCOUNTS_READ,
        PersonalAccessTokenScope.ACCOUNTS_WRITE,
        PersonalAccessTokenScope.POLICIES_READ,
        PersonalAccessTokenScope.POLICIES_WRITE,
    }
)


class PersonalAccessTokenState(StrEnum):
    ACTIVE = 'active'
    EXPIRED = 'expired'
    REVOKED = 'revoked'


def normalize_token_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError('Personal access token name cannot be empty.')
    return name


class CreatePersonalAccessTokenParams(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1, max_length=64)
    scopes: list[PersonalAccessTokenScope] = Field(min_length=1, max_length=len(PersonalAccessTokenScope))
    expires_at: AwareDatetime | None = None

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return normalize_token_name(value)

    @field_validator('scopes')
    @classmethod
    def normalize_scopes(cls, value: list[PersonalAccessTokenScope]) -> list[PersonalAccessTokenScope]:
        if len(value) != len(set(value)):
            raise ValueError('Personal access token scopes must be unique.')
        return value


class PersonalAccessTokenListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    state: PersonalAccessTokenState | None = None


class PersonalAccessTokenItem(BaseModel):
    id: str
    name: str
    token_prefix: str
    scopes: list[PersonalAccessTokenScope]
    state: PersonalAccessTokenState
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CreatedPersonalAccessToken(PersonalAccessTokenItem):
    token: str = Field(min_length=1, max_length=128)


class PersonalAccessTokenList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    active: int
    max_active: int
    items: list[PersonalAccessTokenItem]


class RevokedPersonalAccessToken(BaseModel):
    id: str
    revoked: bool
    revoked_at: datetime
