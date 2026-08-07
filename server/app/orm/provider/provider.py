from tortoise import fields
from tortoise.indexes import Index
from tortoise.migrations.constraints import UniqueConstraint

from app.model.provider import ProviderSyncStatus, ProviderVendor
from app.orm.account.account import Account
from app.orm.mixin import GuidMixin, TimestampMixin


class Provider(GuidMixin, TimestampMixin):
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        'models.Account',
        related_name='providers',
    )
    account_id: str
    name = fields.CharField(max_length=128)
    vendor = fields.CharEnumField(ProviderVendor, max_length=32)
    enabled = fields.BooleanField(default=True)
    sync_enabled = fields.BooleanField(default=False)
    next_sync_at = fields.DatetimeField(null=True)
    encrypted_credential = fields.TextField()
    settings = fields.JSONField(default=dict)
    only_networks = fields.JSONField(default=list)
    ignore_networks = fields.JSONField(default=list)
    last_sync_at = fields.DatetimeField(null=True)
    last_sync_status = fields.CharEnumField(ProviderSyncStatus, default=ProviderSyncStatus.NEVER, max_length=32)
    last_sync_error = fields.TextField(null=True)
    last_sync_created = fields.IntField(default=0)
    last_sync_updated = fields.IntField(default=0)
    last_sync_restored = fields.IntField(default=0)
    last_sync_archived = fields.IntField(default=0)
    last_sync_skipped = fields.IntField(default=0)
    version = fields.IntField(default=1)

    class Meta:
        table = 'provider'
        constraints = (
            UniqueConstraint(
                fields=('account', 'name'),
                name='uq_provider_active_account_name',
                condition='deleted_at IS NULL',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'deleted_at', 'vendor', 'enabled'), name='idx_provider_account_vendor'),
            Index(fields=('account_id', 'deleted_at', 'created_at'), name='idx_provider_account_order'),
            Index(fields=('deleted_at', 'enabled', 'sync_enabled', 'next_sync_at'), name='idx_provider_sync_due'),
        )

    def model_dump(self) -> dict:
        return {
            'id': self.id,
            'account_id': self.account_id,
            'name': self.name,
            'vendor': ProviderVendor(self.vendor),
            'enabled': self.enabled,
            'sync_enabled': self.sync_enabled,
            'credential': {'has_secret': bool(self.encrypted_credential)},
            'settings': self.settings if isinstance(self.settings, dict) else {},
            'only_networks': self.only_networks if isinstance(self.only_networks, list) else [],
            'ignore_networks': self.ignore_networks if isinstance(self.ignore_networks, list) else [],
            'last_sync_at': self.last_sync_at,
            'last_sync_status': ProviderSyncStatus(self.last_sync_status),
            'last_sync_error': self.last_sync_error,
            'last_sync_created': self.last_sync_created,
            'last_sync_updated': self.last_sync_updated,
            'last_sync_restored': self.last_sync_restored,
            'last_sync_archived': self.last_sync_archived,
            'last_sync_skipped': self.last_sync_skipped,
            'version': self.version,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
        }
