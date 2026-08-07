from tortoise import fields
from tortoise.indexes import Index

from app.model.account.role import AccountRole
from app.model.account.status import AccountStatus
from app.orm.mixin import GuidMixin, TimestampMixin


class Account(GuidMixin, TimestampMixin):
    email = fields.CharField(max_length=320, unique=True)
    role = fields.CharEnumField(AccountRole, default=AccountRole.USER, max_length=32)
    status = fields.CharEnumField(AccountStatus, default=AccountStatus.UNACTIVATED, max_length=32)
    password_hash = fields.CharField(max_length=255, null=True)
    name = fields.CharField(max_length=255, null=True)
    avatar_url = fields.CharField(max_length=1024, null=True)
    first_login_at = fields.DatetimeField(null=True)
    last_login_at = fields.DatetimeField(null=True)
    last_login_ip = fields.CharField(max_length=64, null=True)
    last_login_user_agent = fields.CharField(max_length=512, null=True)

    class Meta:
        table = 'account'
        indexes = (
            Index(fields=('deleted_at', 'role', 'status', 'first_login_at', 'created_at'), name='idx_account_admin_list'),
        )

    def model_dump(self) -> dict:
        return {
            'id': self.id,
            'email': self.email,
            'role': AccountRole(self.role),
            'status': AccountStatus(self.status),
            'name': self.name,
            'avatar_url': self.avatar_url,
            'first_login_at': self.first_login_at,
            'last_login_at': self.last_login_at,
            'last_login_ip': self.last_login_ip,
            'last_login_user_agent': self.last_login_user_agent,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
        }
