from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0002_auto_20260731_0738')]

    initial = False

    operations = [
        ops.AddField(
            model_name='App',
            name='provider',
            field=fields.ForeignKeyField(
                'models.Provider',
                source_field='provider_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name='apps',
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.AddIndex(
            model_name='App',
            index=Index(fields=['provider_id', 'deleted_at'], name='idx_app_provider'),
        ),
        ops.AddField(
            model_name='HttpApiRouteTarget',
            name='source_provider',
            field=fields.ForeignKeyField(
                'models.Provider',
                source_field='source_provider_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name='http_api_route_targets',
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.AddIndex(
            model_name='HttpApiRouteTarget',
            index=Index(fields=['source_provider_id', 'deleted_at'], name='idx_http_api_route_target_provider'),
        ),
        ops.AddField(
            model_name='JsonRpcRouteTarget',
            name='source_provider',
            field=fields.ForeignKeyField(
                'models.Provider',
                source_field='source_provider_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name='jsonrpc_route_targets',
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.AddIndex(
            model_name='JsonRpcRouteTarget',
            index=Index(fields=['source_provider_id', 'deleted_at'], name='idx_jsonrpc_route_target_provider'),
        ),
    ]
