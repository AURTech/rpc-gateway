from app.model.transport import Transport
from tortoise import fields, migrations
from tortoise.migrations import operations as ops

FORWARD_SQL = """
TRUNCATE TABLE system_jsonrpc_cache_payload, system_jsonrpc_cache_payload_lease RESTART IDENTITY;
ALTER TABLE system_jsonrpc_cache_payload RENAME TO system_cache_payload;
ALTER TABLE system_jsonrpc_cache_payload_lease RENAME TO system_cache_payload_lease;
"""

REVERSE_SQL = """
TRUNCATE TABLE system_cache_payload, system_cache_payload_lease RESTART IDENTITY;
ALTER TABLE system_cache_payload RENAME TO system_jsonrpc_cache_payload;
ALTER TABLE system_cache_payload_lease RENAME TO system_jsonrpc_cache_payload_lease;
"""


class Migration(migrations.Migration):
    dependencies = [('models', '0007_provider_networks')]

    initial = False

    # Reason: tortoise migration operation subclasses are narrower than the base annotation in its type stubs.
    operations = [  # pyright: ignore[reportAssignmentType]
        ops.RunSQL(FORWARD_SQL, REVERSE_SQL),
        ops.RenameModel('SystemJsonRpcCachePayload', 'SystemCachePayload'),
        ops.AlterModelOptions(
            name='SystemCachePayload',
            options={'table': 'system_cache_payload'},
        ),
        ops.RenameField('SystemCachePayload', 'method', 'operation'),
        ops.AddField(
            model_name='SystemCachePayload',
            name='transport',
            # Reason: tortoise types CharEnumField as the enum member instead of the runtime field instance.
            field=fields.CharEnumField(enum_type=Transport, max_length=16),  # pyright: ignore[reportArgumentType]
        ),
        ops.RunSQL(
            'ALTER TABLE system_cache_payload DROP CONSTRAINT uid_system_json_chain_61a00a; '
            'ALTER TABLE system_cache_payload ADD CONSTRAINT uq_system_cache_payload_identity '
            'UNIQUE (transport, chain, network, operation, cache_key);',
            'ALTER TABLE system_cache_payload DROP CONSTRAINT uq_system_cache_payload_identity; '
            'ALTER TABLE system_cache_payload ADD CONSTRAINT uid_system_json_chain_61a00a '
            'UNIQUE (chain, network, operation, cache_key);',
        ),
        ops.AlterModelOptions(
            name='SystemCachePayload',
            options={'unique_together': (('transport', 'chain', 'network', 'operation', 'cache_key'),)},
        ),
        ops.RenameConstraint(
            model_name='SystemCachePayload',
            old_name='chk_system_jsonrpc_cache_payload_size',
            new_name='chk_system_cache_payload_size',
        ),
        ops.RunSQL(
            'ALTER TABLE system_cache_payload RENAME CONSTRAINT '
            'chk_system_jsonrpc_cache_stored_size TO chk_system_cache_stored_size;',
            'ALTER TABLE system_cache_payload RENAME CONSTRAINT '
            'chk_system_cache_stored_size TO chk_system_jsonrpc_cache_stored_size;',
        ),
        ops.RenameIndex(
            model_name='SystemCachePayload',
            old_name='idx_system_jsonrpc_cache_payload_retention',
            new_name='idx_system_cache_payload_retention',
        ),
        ops.RenameModel('SystemJsonRpcCachePayloadLease', 'SystemCachePayloadLease'),
        ops.AlterModelOptions(
            name='SystemCachePayloadLease',
            options={'table': 'system_cache_payload_lease'},
        ),
        ops.RenameField('SystemCachePayloadLease', 'method', 'operation'),
        ops.AddField(
            model_name='SystemCachePayloadLease',
            name='transport',
            # Reason: tortoise types CharEnumField as the enum member instead of the runtime field instance.
            field=fields.CharEnumField(enum_type=Transport, max_length=16),  # pyright: ignore[reportArgumentType]
        ),
        ops.RunSQL(
            'ALTER TABLE system_cache_payload_lease DROP CONSTRAINT uid_system_json_chain_44ff7a; '
            'ALTER TABLE system_cache_payload_lease ADD CONSTRAINT uq_system_cache_payload_lease_identity '
            'UNIQUE (transport, chain, network, operation, cache_key);',
            'ALTER TABLE system_cache_payload_lease DROP CONSTRAINT uq_system_cache_payload_lease_identity; '
            'ALTER TABLE system_cache_payload_lease ADD CONSTRAINT uid_system_json_chain_44ff7a '
            'UNIQUE (chain, network, operation, cache_key);',
        ),
        ops.AlterModelOptions(
            name='SystemCachePayloadLease',
            options={'unique_together': (('transport', 'chain', 'network', 'operation', 'cache_key'),)},
        ),
        ops.RenameIndex(
            model_name='SystemCachePayloadLease',
            old_name='idx_system_jsonrpc_cache_payload_lease_expiry',
            new_name='idx_system_cache_payload_lease_expiry',
        ),
    ]
