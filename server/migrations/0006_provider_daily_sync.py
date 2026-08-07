from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops

FORWARD_SQL = """
WITH provider_slots AS (
    SELECT
        id,
        (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
            + (
                (
                    get_byte(sha256(convert_to(account_id, 'UTF8')), 0) * 256
                    + get_byte(sha256(convert_to(account_id, 'UTF8')), 1)
                ) % 96
            ) * INTERVAL '15 minutes' AS slot_at
    FROM provider
    WHERE deleted_at IS NULL
      AND enabled = TRUE
      AND sync_enabled = TRUE
)
UPDATE provider
SET next_sync_at = CASE
    WHEN provider_slots.slot_at > CURRENT_TIMESTAMP THEN provider_slots.slot_at
    ELSE provider_slots.slot_at + INTERVAL '1 day'
END
FROM provider_slots
WHERE provider.id = provider_slots.id;
"""

REVERSE_SQL = 'UPDATE provider SET next_sync_at = NULL;'


class Migration(migrations.Migration):
    dependencies = [('models', '0005_compress_system_cache_payload')]

    initial = False

    operations = [
        ops.RemoveIndex(model_name='Provider', name='idx_provider_sync_due'),
        ops.AddField(
            model_name='Provider',
            name='next_sync_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.RunSQL(FORWARD_SQL, REVERSE_SQL),
        ops.AddIndex(
            model_name='Provider',
            index=Index(
                fields=['deleted_at', 'enabled', 'sync_enabled', 'next_sync_at'],
                name='idx_provider_sync_due',
            ),
        ),
        ops.RemoveField(model_name='Provider', name='sync_interval_seconds'),
    ]
