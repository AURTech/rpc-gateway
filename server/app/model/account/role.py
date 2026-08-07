from enum import StrEnum


class AccountRole(StrEnum):
    ADMIN = 'admin'
    USER = 'user'

    @property
    def label(self) -> str:
        match self:
            case AccountRole.ADMIN:
                return 'Admin'
            case AccountRole.USER:
                return 'User'
