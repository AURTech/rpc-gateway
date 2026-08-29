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
    'gateway_usage_endpoint_five_minute',
    'gateway_usage_endpoint_hourly',
    'gateway_usage_five_minute',
    'gateway_usage_hourly',
    'gateway_usage_method_five_minute',
    'gateway_usage_method_hourly',
    'gateway_usage_metric_availability',
    'gateway_usage_rollup_hour',
    'gateway_usage_route_five_minute',
    'gateway_usage_route_hourly',
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
    'provider_sync_run',
    'provider_sync_run_item',
    'system_cache_payload',
    'system_cache_payload_lease',
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
                  AND relation.relname = 'system_cache_payload'
                """,
                schema,
            )
            stored_size_nullable = await connection.fetchval(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name = 'system_cache_payload'
                  AND column_name = 'stored_size'
                """,
                schema,
            )
            cache_transport_nullable = await connection.fetchval(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name = 'system_cache_payload'
                  AND column_name = 'transport'
                """,
                schema,
            )
            route_latency_columns = await connection.fetch(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name IN ('http_api_route', 'jsonrpc_route')
                  AND column_name = 'max_latency_ms'
                """,
                schema,
            )
            endpoint_classification_columns = await connection.fetch(
                """
                SELECT table_name, column_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name IN ('gateway_usage_endpoint_five_minute', 'gateway_usage_endpoint_hourly')
                  AND column_name IN ('first_attempts', 'retry_attempts')
                ORDER BY table_name, column_name
                """,
                schema,
            )
            availability_rows = await connection.fetch(
                f'SELECT metric, coverage_start_at FROM "{schema}".gateway_usage_metric_availability ORDER BY metric'
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
        assert 'chk_system_cache_payload_size' in constraint_names
        assert 'chk_system_cache_stored_size' in constraint_names
        assert 'chk_gateway_usage_hourly_outcomes' in constraint_names
        assert 'chk_gateway_usage_method_hourly_outcomes' in constraint_names
        assert 'chk_gateway_usage_five_minute_outcomes' in constraint_names
        assert 'chk_gateway_usage_method_five_minute_outcomes' in constraint_names
        assert 'chk_gateway_usage_endpoint_five_classification' in constraint_names
        assert 'chk_gateway_usage_endpoint_five_attempts' in constraint_names
        assert 'chk_gateway_usage_endpoint_hour_classification' in constraint_names
        assert 'chk_gateway_usage_endpoint_hour_attempts' in constraint_names
        assert 'chk_gateway_usage_route_five_outcomes' in constraint_names
        assert 'chk_gateway_usage_route_hour_outcomes' in constraint_names
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
            '0006_provider_daily_sync',
            '0007_provider_networks',
            '0008_endpoint_usage',
            '0008_system_cache_transport',
            '0009_endpoint_usage_scope_indexes',
            '0010_auto_20260817_0257',
            '0011_provider_cleanup',
            '0012_account_status_activation',
            '0013_remove_endpoint_trust',
            '0014_remove_route_latency_limit',
            '0015_route_aware_usage',
        ]
        assert cache_transport_nullable == 'NO'
        assert route_latency_columns == []
        assert len(endpoint_classification_columns) == 4
        assert all(row['is_nullable'] == 'YES' for row in endpoint_classification_columns)
        assert all(row['column_default'] is None for row in endpoint_classification_columns)
        assert [str(row['metric']) for row in availability_rows] == [
            'endpoint_attempt_classification',
            'route_usage',
        ]
        assert all(row['coverage_start_at'] is None for row in availability_rows)
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


@pytest.mark.anyio
async def test_route_aware_usage_migration_preserves_unknown_classification() -> None:
    schema = f'test_{uuid4().hex}'
    await create_schema(schema)
    try:
        await migrate_schema(schema, target='models.0014_remove_route_latency_limit')
        connection = await _connect_test_database()
        bucket = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        try:
            for table, bucket_column in (
                ('gateway_usage_endpoint_five_minute', 'bucket_start'),
                ('gateway_usage_endpoint_hourly', 'bucket_hour'),
            ):
                await connection.execute(
                    f"""
                    INSERT INTO "{schema}".{table} (
                        id, account_id, app_id, gateway_id, route_id, endpoint_id, chain, network,
                        {bucket_column}, total_attempts, created_at, modified_at
                    ) VALUES (
                        $1, 'account-1', 'app-1', 'gateway-1', 'route-1', 'endpoint-1',
                        'ethereum', 'mainnet', $2, 5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """,
                    f'historical-{bucket_column}'[:21],
                    bucket,
                )
        finally:
            await connection.close()

        await migrate_schema(schema)
        connection = await _connect_test_database()
        try:
            rows = await connection.fetch(
                f"""
                SELECT first_attempts, retry_attempts
                FROM "{schema}".gateway_usage_endpoint_five_minute
                UNION ALL
                SELECT first_attempts, retry_attempts
                FROM "{schema}".gateway_usage_endpoint_hourly
                """
            )
            coverage = await connection.fetch(
                f'SELECT metric, coverage_start_at FROM "{schema}".gateway_usage_metric_availability'
            )
        finally:
            await connection.close()
        assert len(rows) == 2
        assert all(row['first_attempts'] is None and row['retry_attempts'] is None for row in rows)
        assert {str(row['metric']) for row in coverage} == {'route_usage', 'endpoint_attempt_classification'}
        assert all(row['coverage_start_at'] is None for row in coverage)

        await migrate_schema(schema, target='models.0014_remove_route_latency_limit')
        connection = await _connect_test_database()
        try:
            availability_table = await connection.fetchval(
                'SELECT to_regclass($1)', f'{schema}.gateway_usage_metric_availability'
            )
            classification_columns = await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name IN ('gateway_usage_endpoint_five_minute', 'gateway_usage_endpoint_hourly')
                  AND column_name IN ('first_attempts', 'retry_attempts')
                """,
                schema,
            )
        finally:
            await connection.close()
        assert availability_table is None
        assert classification_columns == []

        await migrate_schema(schema)
        connection = await _connect_test_database()
        try:
            reapplied_coverage = await connection.fetch(
                f'SELECT metric, coverage_start_at FROM "{schema}".gateway_usage_metric_availability'
            )
        finally:
            await connection.close()
        assert {str(row['metric']) for row in reapplied_coverage} == {
            'route_usage',
            'endpoint_attempt_classification',
        }
        assert all(row['coverage_start_at'] is None for row in reapplied_coverage)
    finally:
        await drop_schema(schema)


@pytest.mark.anyio
async def test_system_cache_transport_migration_round_trip() -> None:
    schema = f'test_{uuid4().hex}'
    await create_schema(schema)
    try:
        await migrate_schema(schema, target='models.0007_provider_networks')
        await migrate_schema(schema)
        connection = await _connect_test_database()
        try:
            applied_columns = await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = 'system_cache_payload'
                """,
                schema,
            )
        finally:
            await connection.close()
        assert {str(row['column_name']) for row in applied_columns} >= {'transport', 'operation'}

        await migrate_schema(schema, target='models.0007_provider_networks')
        connection = await _connect_test_database()
        try:
            restored_columns = await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = 'system_jsonrpc_cache_payload'
                """,
                schema,
            )
        finally:
            await connection.close()
        restored = {str(row['column_name']) for row in restored_columns}
        assert 'method' in restored
        assert 'transport' not in restored

        await migrate_schema(schema)
        connection = await _connect_test_database()
        try:
            reapplied = await connection.fetchval(
                """
                SELECT to_regclass($1)
                """,
                f'{schema}.system_cache_payload',
            )
        finally:
            await connection.close()
        assert reapplied is not None
    finally:
        await drop_schema(schema)
