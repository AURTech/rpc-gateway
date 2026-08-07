from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from app.core.config import CONF
from tests.infra import create_schema, drop_schema, migrate_schema, split_orm_url

BUSINESS_TABLES = {
    'account',
    'app',
    'app_api_key',
    'app_audit_event',
    'auth',
    'auth_session',
    'endpoint',
    'endpoint_audit_event',
    'gateway',
    'gateway_usage_checkpoint',
    'gateway_usage_five_minute',
    'gateway_usage_hourly',
    'gateway_usage_method_five_minute',
    'gateway_usage_method_hourly',
    'gateway_usage_rollup_hour',
    'http_api_rate_limit_policy',
    'http_api_rate_limit_policy_audit_event',
    'http_api_route',
    'http_api_route_target',
    'jsonrpc_rate_limit_policy',
    'jsonrpc_rate_limit_policy_audit_event',
    'jsonrpc_route',
    'jsonrpc_route_scope',
    'jsonrpc_route_target',
    'personal_access_token',
    'provider',
    'provider_endpoint_binding',
    'system_jsonrpc_cache_payload',
    'system_jsonrpc_cache_payload_lease',
}


async def _connect_test_database() -> asyncpg.Connection:
    return await asyncpg.connect(dsn=split_orm_url(CONF.TEST_ORM_URL).base_url)


@pytest.mark.anyio
async def test_initial_migration_creates_v2_schema() -> None:
    schema = f'test_{uuid4().hex}'
    await create_schema(schema)
    try:
        await migrate_schema(schema)
        connection = await _connect_test_database()
        try:
            rows = await connection.fetch(
                """
                SELECT relation.relname AS table_name
                FROM pg_class AS relation
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = $1
                  AND relation.relkind IN ('r', 'p')
                  AND NOT relation.relispartition
                  AND relation.relname <> 'tortoise_migrations'
                """,
                schema,
            )
            constraints = await connection.fetch(
                'SELECT conname FROM pg_constraint WHERE connamespace = $1::regnamespace',
                schema,
            )
            provider_index = await connection.fetchval(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = $1
                  AND indexname = 'uq_provider_active_account_name'
                """,
                schema,
            )
            payload_persistence = await connection.fetchval(
                """
                SELECT relation.relpersistence
                FROM pg_class AS relation
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = $1
                  AND relation.relname = 'system_jsonrpc_cache_payload'
                """,
                schema,
            )
            stored_size_nullable = await connection.fetchval(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name = 'system_jsonrpc_cache_payload'
                  AND column_name = 'stored_size'
                """,
                schema,
            )
            migration_names = await connection.fetch(
                f'SELECT name FROM "{schema}".tortoise_migrations ORDER BY name',
            )
            partition_count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM pg_inherits
                JOIN pg_class AS parent ON parent.oid = pg_inherits.inhparent
                JOIN pg_namespace AS namespace ON namespace.oid = parent.relnamespace
                WHERE namespace.nspname = $1
                  AND parent.relname IN (
                      'gateway_usage_hourly',
                      'gateway_usage_method_hourly',
                      'gateway_usage_five_minute',
                      'gateway_usage_method_five_minute'
                  )
                """,
                schema,
            )
            old_reference = datetime.now(UTC) - timedelta(days=800)
            old_result = await connection.fetchrow(
                f'SELECT * FROM "{schema}".gateway_usage_maintain_partitions($1, $2)',
                old_reference,
                18,
            )
            retention_result = await connection.fetchrow(
                f'SELECT * FROM "{schema}".gateway_usage_maintain_partitions($1, $2)',
                datetime.now(UTC),
                18,
            )
            fine_old_result = await connection.fetchrow(
                f'SELECT * FROM "{schema}".gateway_usage_fine_maintain_partitions($1, $2)',
                old_reference,
                48,
            )
            fine_retention_result = await connection.fetchrow(
                f'SELECT * FROM "{schema}".gateway_usage_fine_maintain_partitions($1, $2)',
                datetime.now(UTC),
                48,
            )
        finally:
            await connection.close()
        tables = {str(row['table_name']) for row in rows}
        constraint_names = {str(row['conname']) for row in constraints}
        assert tables == BUSINESS_TABLES
        assert 'chk_endpoint_auth_columns' in constraint_names
        assert 'chk_system_jsonrpc_cache_payload_size' in constraint_names
        assert 'chk_system_jsonrpc_cache_stored_size' in constraint_names
        assert 'chk_gateway_usage_hourly_outcomes' in constraint_names
        assert 'chk_gateway_usage_method_hourly_outcomes' in constraint_names
        assert 'chk_gateway_usage_five_minute_outcomes' in constraint_names
        assert 'chk_gateway_usage_method_five_minute_outcomes' in constraint_names
        assert provider_index is not None
        assert 'WHERE (deleted_at IS NULL)' in provider_index
        assert payload_persistence == b'u'
        assert stored_size_nullable == 'NO'
        assert [str(row['name']) for row in migration_names] == [
            '0001_initial',
            '0002_auto_20260731_0738',
            '0003_auto_20260803_0711',
            '0004_personal_access_tokens',
            '0005_compress_system_cache_payload',
        ]
        assert partition_count == 14
        assert old_result is not None
        assert old_result['created_partitions'] == 6
        assert retention_result is not None
        assert retention_result['dropped_partitions'] >= 6
        assert fine_old_result is not None
        assert fine_old_result['created_partitions'] == 8
        assert fine_retention_result is not None
        assert fine_retention_result['dropped_partitions'] >= 8
        assert not any(table.startswith('rpc_') for table in tables)
        assert 'runtime_config' not in tables
    finally:
        await drop_schema(schema)
