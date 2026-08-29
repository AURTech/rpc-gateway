from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index

from app.model.provider_state import ProviderEndpointAction, ProviderSyncRunState, ProviderSyncTrigger
from app.orm.mixin import GuidMixin, TimestampMixin
from app.orm.provider.provider import Provider


class ProviderSyncRun(GuidMixin, TimestampMixin):
    provider: fields.ForeignKeyRelation[Provider] = fields.ForeignKeyField(
        'models.Provider', related_name='sync_runs', on_delete=OnDelete.CASCADE
    )
    provider_id: str
    account_id = fields.CharField(max_length=21)
    trigger = fields.CharEnumField(ProviderSyncTrigger, max_length=16)
    state = fields.CharEnumField(ProviderSyncRunState, max_length=16, default=ProviderSyncRunState.QUEUED)
    queued_at = fields.DatetimeField()
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created = fields.IntField(default=0)
    updated = fields.IntField(default=0)
    restored = fields.IntField(default=0)
    archived = fields.IntField(default=0)
    skipped = fields.IntField(default=0)
    route_targets_added = fields.IntField(default=0)
    route_targets_removed = fields.IntField(default=0)
    route_targets_skipped = fields.IntField(default=0)
    error = fields.TextField(null=True)

    class Meta:
        table = 'provider_sync_run'
        indexes = (
            Index(fields=('provider_id', 'created_at'), name='idx_provider_sync_run_provider_created'),
            Index(fields=('provider_id', 'state'), name='idx_provider_sync_run_provider_state'),
        )


class ProviderSyncRunItem(GuidMixin, TimestampMixin):
    run: fields.ForeignKeyRelation[ProviderSyncRun] = fields.ForeignKeyField(
        'models.ProviderSyncRun', related_name='items', on_delete=OnDelete.CASCADE
    )
    run_id: str
    action = fields.CharEnumField(ProviderEndpointAction, max_length=16)
    chain = fields.CharField(max_length=32, null=True)
    network = fields.CharField(max_length=32, null=True)
    endpoint_id = fields.CharField(max_length=21, null=True)
    external_id = fields.CharField(max_length=512, null=True)
    error = fields.TextField(null=True)

    class Meta:
        table = 'provider_sync_run_item'
        indexes = (Index(fields=('run_id', 'created_at'), name='idx_provider_sync_run_item_run_created'),)
