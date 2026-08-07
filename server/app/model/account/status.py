from enum import StrEnum


class AccountStatus(StrEnum):
    UNACTIVATED = 'unactivated'
    ACTIVE = 'active'
    DISABLED = 'disabled'
    ARCHIVED = 'archived'

    @property
    def label(self) -> str:
        match self:
            case AccountStatus.UNACTIVATED:
                return 'Unactivated'
            case AccountStatus.ACTIVE:
                return 'Active'
            case AccountStatus.DISABLED:
                return 'Disabled'
            case AccountStatus.ARCHIVED:
                return 'Archived'


ACCOUNT_STATUS_UPDATE_STATUSES = frozenset({AccountStatus.ACTIVE, AccountStatus.DISABLED})
