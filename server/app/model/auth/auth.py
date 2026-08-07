from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.model.auth.token import PersonalAccessTokenScope


class IdentityType(StrEnum):
    ADMIN = 'admin'
    USER = 'user'


class AuthProvider(StrEnum):
    GOOGLE = 'google'


class AuthIdentity(BaseModel):
    identity_type: IdentityType
    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
    pat_id: str | None = Field(default=None, exclude=True)
    pat_scopes: frozenset[PersonalAccessTokenScope] = Field(default_factory=frozenset, exclude=True)

    @property
    def uses_pat(self) -> bool:
        return self.pat_id is not None


class LoginResult(BaseModel):
    identity_type: IdentityType
    id: str
    email: str
    expires_at: datetime


class LogoutResult(BaseModel):
    logged_out: bool


class PasswordLoginParams(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class SetPasswordParams(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)
    old_password: str | None = Field(default=None, max_length=128)


class PasswordResult(BaseModel):
    updated: bool
