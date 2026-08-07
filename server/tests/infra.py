import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg
from app.core.config import CONF
from app.infra.cache import init_cache
from app.infra.db import (
    DEFAULT_DB_CONNECTION,
    SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    SYSTEM_CACHE_RETENTION_DB_CONNECTION,
)
from app.services.base import Manager
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis
from tortoise import Tortoise, fields
from tortoise.migrations.api import migrate
from tortoise.migrations.recorder import MigrationRecorder
from tortoise.models import Model

TEST_SCHEMA_RE = re.compile(r'^test_[a-f0-9]{32}$')

TEST_PROJECT_NAMESPACE = f'{CONF.PROJECT_NAME}-test'
TRUNCATE_EXCLUDED_TABLES = frozenset({'aerich', 'gateway_usage_checkpoint', 'tortoise_migrations'})
_migration_recorder_patched = False


@dataclass(frozen=True)
class _ParsedOrmUrl:
    parsed: SplitResult
    database: str
    query: dict[str, str]
    base_url: str


@lru_cache(maxsize=1)
def split_orm_url(url: str) -> _ParsedOrmUrl:
    parsed = urlsplit(url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise RuntimeError('Tests require TEST_ORM_URL to use postgres:// or postgresql://.')
    database = parsed.path.lstrip('/')
    if 'test' not in database.lower():
        raise RuntimeError('Refusing to run tests against a non-test PostgreSQL database.')
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop('schema', None)
    base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return _ParsedOrmUrl(parsed=parsed, database=database, query=query, base_url=base_url)


@lru_cache(maxsize=1)
def redis_db_index(url: str) -> int:
    parsed = urlsplit(url)
    if parsed.scheme not in {'redis', 'rediss'}:
        raise RuntimeError('Tests require TEST_REDIS_URL to use redis:// or rediss://.')
    db_path = parsed.path.lstrip('/')
    return int(db_path or '0')


def configure_test_runtime() -> None:
    split_orm_url(CONF.TEST_ORM_URL)
    if redis_db_index(CONF.TEST_REDIS_URL) == 0:
        raise RuntimeError('Refusing to run tests against Redis DB 0.')
    CONF.ORM_URL = CONF.TEST_ORM_URL
    CONF.REDIS_URL = CONF.TEST_REDIS_URL
    CONF.PROJECT_NAME = TEST_PROJECT_NAMESPACE
    CONF.ENDPOINT_ACTIVE_KEY_VERSION = 'v1'
    CONF.ENDPOINT_KEYRING = {'v1': SecretStr('test-endpoint-master-key-32-bytes')}
    CONF.AUTH_PAT_HASH_SECRET = 'test-pat-hash-secret-value-32-bytes'


def _make_migration_record_model(_recorder: MigrationRecorder, table_name: str) -> type[Model]:
    class MigrationRecord(Model):
        id = fields.IntField(primary_key=True)
        app = fields.CharField(max_length=255)
        name = fields.CharField(max_length=255)
        applied_at = fields.DatetimeField()

        class Meta:
            table = table_name
            app = '_migrations'
            unique_together = (('app', 'name'),)

    return MigrationRecord


def patch_tortoise_migration_recorder() -> None:
    global _migration_recorder_patched
    if _migration_recorder_patched:
        return
    # Reason: Tortoise exposes this as a private method, but the test harness must override its table schema.
    MigrationRecorder._make_model = _make_migration_record_model  # ty: ignore[invalid-assignment]
    _migration_recorder_patched = True


def _build_test_orm_url(schema: str) -> str:
    info = split_orm_url(CONF.TEST_ORM_URL)
    query = info.query.copy()
    query['schema'] = schema
    parsed = info.parsed
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _build_test_orm_config(schema: str) -> dict[str, Any]:
    return {
        'connections': {'default': _build_test_orm_url(schema)},
        'apps': {
            'models': {
                'models': ['app.orm'],
                'default_connection': 'default',
                'migrations': 'migrations',
            },
        },
    }


def build_test_orm_config(schema: str) -> dict[str, Any]:
    config = _build_test_orm_config(schema)
    url = _build_test_orm_url(schema)
    config['connections'] = {
        DEFAULT_DB_CONNECTION: url,
        SYSTEM_CACHE_RETENTION_DB_CONNECTION: url,
        SYSTEM_CACHE_COORDINATION_DB_CONNECTION: url,
    }
    return config


def _quote_schema(schema: str) -> str:
    if not TEST_SCHEMA_RE.fullmatch(schema):
        raise RuntimeError(f'Unsafe test schema name: {schema}')
    return f'"{schema}"'


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _run_admin_sql(sql: str) -> None:
    connection = await asyncpg.connect(dsn=split_orm_url(CONF.TEST_ORM_URL).base_url)
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


async def create_schema(schema: str) -> None:
    await _run_admin_sql(f'CREATE SCHEMA {_quote_schema(schema)}')


async def drop_schema(schema: str) -> None:
    await _run_admin_sql(f'DROP SCHEMA IF EXISTS {_quote_schema(schema)} CASCADE')


async def migrate_schema(schema: str, *, target: str | None = None) -> dict[str, Any]:
    patch_tortoise_migration_recorder()
    config = _build_test_orm_config(schema)
    try:
        await migrate(config=config, target=target)
    finally:
        await Tortoise.close_connections()
    return config


async def _list_truncated_tables(schema: str) -> list[str]:
    connection = await asyncpg.connect(dsn=split_orm_url(CONF.TEST_ORM_URL).base_url)
    try:
        rows = await connection.fetch(
            """
            SELECT relation.relname AS table_name
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = $1
              AND relation.relkind IN ('r', 'p')
              AND NOT relation.relispartition
            ORDER BY relation.relname
            """,
            schema,
        )
    finally:
        await connection.close()

    return [str(row['table_name']) for row in rows if str(row['table_name']) not in TRUNCATE_EXCLUDED_TABLES]


async def truncate_test_tables(schema: str) -> None:
    if not TEST_SCHEMA_RE.fullmatch(schema):
        raise RuntimeError(f'Unsafe test schema name: {schema}')

    tables = await _list_truncated_tables(schema)
    if not tables:
        return

    quoted_schema = _quote_schema(schema)
    quoted_tables = ', '.join(f'{quoted_schema}.{_quote_identifier(table)}' for table in tables)
    await _run_admin_sql(f'TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE')
    await _run_admin_sql(
        f"UPDATE {quoted_schema}.gateway_usage_checkpoint SET last_stream_id = '0-0', modified_at = CURRENT_TIMESTAMP"
    )


async def clear_test_redis_keys(redis: Redis) -> None:
    keys: list[str] = []
    async for key in redis.scan_iter(match=f'{TEST_PROJECT_NAMESPACE}:*', count=1000):
        keys.append(str(key))
        if len(keys) >= 1000:
            await redis.delete(*keys)
            keys.clear()
    if keys:
        await redis.delete(*keys)


async def setup_test_redis(app: FastAPI) -> Redis:
    redis = Redis.from_url(url=CONF.TEST_REDIS_URL, decode_responses=True, retry_on_timeout=False)
    # Reason: redis.asyncio ping is awaitable at runtime; stubs are narrower here.
    if not await redis.ping():  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
        raise RuntimeError('Test Redis is not reachable.')
    await clear_test_redis_keys(redis)
    app.state.redis = redis
    Manager.set_redis(redis)
    init_cache(CONF.TEST_REDIS_URL, TEST_PROJECT_NAMESPACE)
    return redis
