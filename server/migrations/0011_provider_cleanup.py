from tortoise import migrations
from tortoise.migrations import operations as ops

FORWARD_SQL = """
UPDATE personal_access_token
SET scopes = (
    SELECT COALESCE(jsonb_agg(scope), '[]'::jsonb)
    FROM jsonb_array_elements(scopes::jsonb) AS scope
    WHERE scope <> to_jsonb('provider-secrets:read'::text)
)
WHERE scopes::jsonb @> '["provider-secrets:read"]'::jsonb;
"""

REVERSE_SQL = 'SELECT 1;'


class Migration(migrations.Migration):
    dependencies = [('models', '0010_auto_20260817_0257')]

    initial = False

    operations = [
        ops.RunSQL(FORWARD_SQL, REVERSE_SQL),
        ops.RemoveField(model_name='Provider', name='last_sync_error'),
        ops.RemoveField(model_name='Provider', name='last_sync_created'),
        ops.RemoveField(model_name='Provider', name='last_sync_updated'),
        ops.RemoveField(model_name='Provider', name='last_sync_restored'),
        ops.RemoveField(model_name='Provider', name='last_sync_archived'),
        ops.RemoveField(model_name='Provider', name='last_sync_skipped'),
    ]
