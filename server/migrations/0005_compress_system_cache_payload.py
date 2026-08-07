from tortoise import migrations
from tortoise.migrations import operations as ops

FORWARD_SQL = """
TRUNCATE TABLE system_jsonrpc_cache_payload, system_jsonrpc_cache_payload_lease RESTART IDENTITY;
ALTER TABLE system_jsonrpc_cache_payload SET UNLOGGED;
ALTER TABLE system_jsonrpc_cache_payload_lease SET UNLOGGED;
ALTER TABLE system_jsonrpc_cache_payload DROP CONSTRAINT chk_system_jsonrpc_cache_payload_size;
ALTER TABLE system_jsonrpc_cache_payload ADD COLUMN stored_size INTEGER NOT NULL;
ALTER TABLE system_jsonrpc_cache_payload
    ADD CONSTRAINT chk_system_jsonrpc_cache_payload_size CHECK (payload_size >= 0);
ALTER TABLE system_jsonrpc_cache_payload
    ADD CONSTRAINT chk_system_jsonrpc_cache_stored_size CHECK (stored_size = octet_length(payload));
"""

REVERSE_SQL = """
TRUNCATE TABLE system_jsonrpc_cache_payload, system_jsonrpc_cache_payload_lease RESTART IDENTITY;
ALTER TABLE system_jsonrpc_cache_payload DROP CONSTRAINT chk_system_jsonrpc_cache_stored_size;
ALTER TABLE system_jsonrpc_cache_payload DROP CONSTRAINT chk_system_jsonrpc_cache_payload_size;
ALTER TABLE system_jsonrpc_cache_payload DROP COLUMN stored_size;
ALTER TABLE system_jsonrpc_cache_payload
    ADD CONSTRAINT chk_system_jsonrpc_cache_payload_size CHECK (payload_size = octet_length(payload));
ALTER TABLE system_jsonrpc_cache_payload SET LOGGED;
ALTER TABLE system_jsonrpc_cache_payload_lease SET LOGGED;
"""


class Migration(migrations.Migration):
    dependencies = [('models', '0004_personal_access_tokens')]

    initial = False

    operations = [ops.RunSQL(FORWARD_SQL, REVERSE_SQL)]
