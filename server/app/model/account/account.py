from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.model.account.role import AccountRole
from app.model.account.status import ACCOUNT_STATUS_UPDATE_STATUSES, AccountStatus
from app.model.pagination import CreatedAtListParams
from app.util.email import normalize_email


class CreateAccountParams(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)

    @field_validator('email')
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class UpdateAccountStatusParams(BaseModel):
    status: AccountStatus

    @field_validator('status')
    @classmethod
    def validate_status(cls, value: AccountStatus) -> AccountStatus:
        if value not in ACCOUNT_STATUS_UPDATE_STATUSES:
            raise ValueError('Account status can only be active or disabled.')
        return value


AccountIdEntry = Annotated[str, Field(min_length=1, max_length=128)]


def normalize_account_ids(value: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in value:
        account_id = raw.strip()
        if not account_id:
            raise ValueError('Account ids cannot be empty.')
        if account_id in seen:
            continue
        seen.add(account_id)
        result.append(account_id)
    return result


class ArchiveAccountsParams(BaseModel):
    ids: list[AccountIdEntry] = Field(..., min_length=1, max_length=100)

    @field_validator('ids')
    @classmethod
    def validate_ids(cls, value: list[str]) -> list[str]:
        return normalize_account_ids(value)


class AccountBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: AccountRole
    status: AccountStatus
    name: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None

    @computed_field
    @property
    def role_label(self) -> str:
        return self.role.label

    @computed_field
    @property
    def status_label(self) -> str:
        return self.status.label


class AccountDetail(AccountBase):
    first_login_at: datetime | None = None
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    last_login_user_agent: str | None = None
    gateway_count: int = 0
    app_count: int = 0


class AccountList(BaseModel):
    page: int
    size: int
    total: int
    max_page: int
    items: list[AccountBase]


class AccountArchiveResult(BaseModel):
    total: int
    items: list[AccountBase]


class AdminAccountListParams(CreatedAtListParams):
    search: str | None = Field(default=None, min_length=1, max_length=320)
    status: AccountStatus | None = None
    activated: bool | None = None
