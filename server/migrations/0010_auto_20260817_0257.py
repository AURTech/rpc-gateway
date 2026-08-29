import app.orm.mixin
from app.model.provider_state import (
    ProviderEndpointAction,
    ProviderEndpointDiscoveryStatus,
    ProviderSyncRunState,
    ProviderSyncTrigger,
)
from app.orm.mixin import NANOIDField
from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0009_endpoint_usage_scope_indexes')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ProviderSyncRun',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                (
                    'provider',
                    fields.ForeignKeyField(
                        'models.Provider',
                        source_field='provider_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='sync_runs',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('account_id', fields.CharField(max_length=21)),
                (
                    'trigger',
                    fields.CharEnumField(
                        description='MANUAL: manual\nSCHEDULED: scheduled', enum_type=ProviderSyncTrigger, max_length=16
                    ),
                ),
                (
                    'state',
                    fields.CharEnumField(
                        default=ProviderSyncRunState.QUEUED,
                        description='QUEUED: queued\nRUNNING: running\nSUCCESS: success\nPARTIAL: partial\nFAILED: failed',
                        enum_type=ProviderSyncRunState,
                        max_length=16,
                    ),
                ),
                ('queued_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('started_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('completed_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('created', fields.IntField(default=0)),
                ('updated', fields.IntField(default=0)),
                ('restored', fields.IntField(default=0)),
                ('archived', fields.IntField(default=0)),
                ('skipped', fields.IntField(default=0)),
                ('route_targets_added', fields.IntField(default=0)),
                ('route_targets_removed', fields.IntField(default=0)),
                ('route_targets_skipped', fields.IntField(default=0)),
                ('error', fields.TextField(null=True, unique=False)),
            ],
            options={
                'table': 'provider_sync_run',
                'app': 'models',
                'indexes': [
                    Index(fields=['provider_id', 'created_at'], name='idx_provider_sync_run_provider_created'),
                    Index(fields=['provider_id', 'state'], name='idx_provider_sync_run_provider_state'),
                ],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='ProviderSyncRunItem',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                (
                    'run',
                    fields.ForeignKeyField(
                        'models.ProviderSyncRun',
                        source_field='run_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='items',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'action',
                    fields.CharEnumField(
                        description=(
                            'CREATED: created\nUPDATED: updated\nRESTORED: restored\n'
                            'ARCHIVED: archived\nSKIPPED: skipped\nFAILED: failed'
                        ),
                        enum_type=ProviderEndpointAction,
                        max_length=16,
                    ),
                ),
                ('chain', fields.CharField(null=True, max_length=32)),
                ('network', fields.CharField(null=True, max_length=32)),
                ('endpoint_id', fields.CharField(null=True, max_length=21)),
                ('external_id', fields.CharField(null=True, max_length=512)),
                ('error', fields.TextField(null=True, unique=False)),
            ],
            options={
                'table': 'provider_sync_run_item',
                'app': 'models',
                'indexes': [Index(fields=['run_id', 'created_at'], name='idx_provider_sync_run_item_run_created')],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.AddField(
            model_name='ProviderEndpointBinding',
            name='discovery_status',
            field=fields.CharEnumField(
                default=ProviderEndpointDiscoveryStatus.PRESENT,
                description='PRESENT: present\nMISSING: missing',
                enum_type=ProviderEndpointDiscoveryStatus,
                max_length=16,
                null=True,
            ),
        ),
        # Existing bindings predate discovery tracking. Backfill them as present before enforcing
        # the model's non-null invariant; adding the final field directly fails on populated tables.
        ops.RunSQL(
            "UPDATE provider_endpoint_binding SET discovery_status = 'present' WHERE discovery_status IS NULL;",
            'SELECT 1;',
        ),
        ops.AlterField(
            model_name='ProviderEndpointBinding',
            name='discovery_status',
            field=fields.CharEnumField(
                default=ProviderEndpointDiscoveryStatus.PRESENT,
                description='PRESENT: present\nMISSING: missing',
                enum_type=ProviderEndpointDiscoveryStatus,
                max_length=16,
            ),
        ),
        ops.AddField(
            model_name='ProviderEndpointBinding',
            name='missing_since',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
    ]


# pyright: reportArgumentType=false, reportAssignmentType=false
# Reason: Tortoise migration fields use generated schema-state types that are narrower than runtime values.
