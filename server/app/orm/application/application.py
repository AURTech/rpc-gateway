from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index

from app.model.application import AppAuditAction
from app.orm.account.account import Account
from app.orm.mixin import GuidMixin, TimestampMixin


class App(GuidMixin, TimestampMixin):
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        'models.Account',
        related_name='apps',
        on_delete=OnDelete.CASCADE,
    )
    account_id: str
    provider = fields.ForeignKeyField(
        'models.Provider',
        related_name='apps',
        on_delete=OnDelete.SET_NULL,
        null=True,
    )
    provider_id: str | None
    name = fields.CharField(max_length=128)
    enabled = fields.BooleanField(default=True)
    version = fields.IntField(default=1)

    class Meta:
        table = 'app'
        indexes = (
            Index(fields=('account_id', 'deleted_at', 'created_at'), name='idx_app_account_created'),
            Index(fields=('account_id', 'deleted_at', 'enabled'), name='idx_app_account_enabled'),
            Index(fields=('provider_id', 'deleted_at'), name='idx_app_provider'),
        )


class AppApiKey(GuidMixin, TimestampMixin):
    app: fields.ForeignKeyRelation[App] = fields.ForeignKeyField(
        'models.App',
        related_name='api_keys',
        on_delete=OnDelete.CASCADE,
    )
    app_id: str
    api_key_digest = fields.CharField(max_length=64, unique=True)
    encrypted_api_key = fields.TextField()
    expires_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'app_api_key'
        indexes = (Index(fields=('app_id', 'deleted_at', 'created_at'), name='idx_app_api_key_app_created'),)


class AppAuditEvent(GuidMixin):
    app: fields.ForeignKeyRelation[App] = fields.ForeignKeyField(
        'models.App',
        related_name='audit_events',
        on_delete=OnDelete.CASCADE,
    )
    app_id: str
    account_id = fields.CharField(max_length=21)
    actor_id = fields.CharField(max_length=21)
    actor_token_id = fields.CharField(max_length=21, null=True)
    resource_type = fields.CharField(max_length=32)
    resource_id = fields.CharField(max_length=21)
    action = fields.CharEnumField(AppAuditAction, max_length=32)
    previous_version = fields.IntField(null=True)
    new_version = fields.IntField(null=True)
    changed_fields = fields.JSONField(default=list)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'app_audit_event'
        indexes = (
            Index(fields=('app_id', 'created_at'), name='idx_app_audit_app_created'),
            Index(fields=('account_id', 'created_at'), name='idx_app_audit_account_created'),
        )
