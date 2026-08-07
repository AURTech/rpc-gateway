from tortoise import fields
from tortoise.indexes import Index

from app.model.auth import AuthProvider
from app.orm.account.account import Account
from app.orm.mixin import GuidMixin, TimestampMixin


class Auth(GuidMixin, TimestampMixin):
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        'models.Account',
        related_name='auths',
        on_delete=fields.CASCADE,
    )
    account_id: str
    provider = fields.CharEnumField(AuthProvider, max_length=32)
    identifier = fields.CharField(max_length=320)

    class Meta:
        table = 'auth'
        unique_together = (('provider', 'identifier'),)


class AuthSession(GuidMixin, TimestampMixin):
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        'models.Account',
        related_name='auth_sessions',
        on_delete=fields.CASCADE,
    )
    account_id: str
    token_hash = fields.CharField(max_length=128, unique=True)
    expires_at = fields.DatetimeField()
    revoked_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'auth_session'
        indexes = (Index(fields=('account_id', 'deleted_at', 'revoked_at'), name='idx_auth_session_account'),)


class PersonalAccessToken(GuidMixin, TimestampMixin):
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        'models.Account',
        related_name='personal_access_tokens',
        on_delete=fields.CASCADE,
    )
    account_id: str
    name = fields.CharField(max_length=64)
    token_digest = fields.CharField(max_length=64, unique=True)
    token_prefix = fields.CharField(max_length=20)
    scopes = fields.JSONField()
    expires_at = fields.DatetimeField()
    last_used_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'personal_access_token'
        indexes = (
            Index(fields=('account_id', 'deleted_at', 'created_at'), name='idx_personal_access_token_account_created'),
            Index(fields=('account_id', 'deleted_at', 'revoked_at', 'expires_at'), name='idx_personal_access_token_state'),
        )
