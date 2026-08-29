import asyncio
import re
import secrets
import time
from collections.abc import Mapping
from contextlib import AsyncExitStack, suppress
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg
import orjson
from app.core.config import CONF
from app.infra.db import (
    DEFAULT_DB_CONNECTION,
    SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    SYSTEM_CACHE_RETENTION_DB_CONNECTION,
)
from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import JsonRpcForwardingResult, JsonRpcForwardingSuccess
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.model.system_cache import CacheEntry, CacheKey, CacheTier
from app.model.transport import Transport
from app.services.system_cache.flight import PostgresRetentionFlight, RedisTtlFlight, flight_key
from app.services.system_cache.limits import FLIGHT_LEASE_MS
from app.services.system_cache.store import HybridSystemCacheStore, PostgresRetentionStore, RedisTtlStore
from app.services.system_jsonrpc_cache import SystemJsonRpcCacheManager
from app.services.system_jsonrpc_cache.manager import JsonRpcLoader
from app.services.system_jsonrpc_cache.policy import SystemJsonRpcCachePolicy
from redis.asyncio import Redis
from scripts.system_cache_stress.core import CountingLoader
from scripts.system_cache_stress.database import STRESS_DB_POOL_MAX_SIZE, stress_database_connections
from scripts.system_cache_stress.report import ScenarioReport
from scripts.system_cache_stress.workload import WorkloadShape, stress_postgres_retention_workload
from tortoise import Tortoise, connections

_SCHEMA_RE = re.compile(r'^rpc_cache_stress_[a-f0-9]{32}$')
_DATABASE_RE = re.compile(r'^[a-z][a-z0-9_]{0,62}_test$')
_REDIS_GUARD_KEY = 'system-cache-stress:guard'


def _postgres_urls(url: str, schema: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('Stress PostgreSQL URL must use postgres:// or postgresql://.')
    database = parsed.path.lstrip('/')
    if 'test' not in database.casefold():
        raise ValueError('Refusing to use a PostgreSQL database whose name does not contain test.')
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop('schema', None)
    base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    query['schema'] = schema
    # Tortoise accepts postgres:// while asyncpg accepts both supported input schemes.
    schema_url = urlunsplit(('postgres', parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return base_url, schema_url, database


def database_url(url: str, database: str) -> str:
    if _DATABASE_RE.fullmatch(database) is None:
        raise ValueError('Stress PostgreSQL database name must be lowercase, safe, and end with _test.')
    parsed = urlsplit(url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('Application PostgreSQL URL must use postgres:// or postgresql://.')
    active_database = parsed.path.lstrip('/')
    if database == active_database:
        raise ValueError('Stress PostgreSQL database must differ from the application database.')
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database}', parsed.query, parsed.fragment))


def redis_database_url(url: str, database: int) -> str:
    if isinstance(database, bool) or not 1 <= database <= 15:
        raise ValueError('Stress Redis database must be between 1 and 15.')
    parsed = urlsplit(url)
    if parsed.scheme not in {'redis', 'rediss'}:
        raise ValueError('Application Redis URL must use redis:// or rediss://.')
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database}', parsed.query, parsed.fragment))


def _redis_target(url: str) -> tuple[str | None, int, int]:
    parsed = urlsplit(url)
    if parsed.scheme not in {'redis', 'rediss'}:
        raise ValueError('Stress Redis URL must use redis:// or rediss://.')
    path = parsed.path.removeprefix('/')
    if not path.isdecimal() or int(path) == 0:
        raise ValueError('Stress Redis URL must use an explicit non-zero database.')
    return parsed.hostname, parsed.port or 6379, int(path)


async def _prepare_redis(redis_client: Redis) -> str:
    # Reason: redis.asyncio ping is awaitable at runtime; the stub also exposes a synchronous branch.
    await redis_client.ping()  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
    token = secrets.token_urlsafe(16)
    acquired = await redis_client.set(_REDIS_GUARD_KEY, token, nx=True)
    if not acquired:
        raise RuntimeError('Dedicated stress Redis DB is already guarded.')
    if await redis_client.dbsize() != 1:
        await redis_client.delete(_REDIS_GUARD_KEY)
        raise RuntimeError('Dedicated stress Redis DB must be empty.')
    return token


async def _cleanup_redis(redis_client: Redis, *, guard_token: str, namespace: str) -> bool:
    if await redis_client.get(_REDIS_GUARD_KEY) != guard_token:
        return False
    keys = [str(key) async for key in redis_client.scan_iter(match=f'{namespace}:*', count=256)]
    if keys:
        await redis_client.unlink(*keys)
    if await redis_client.get(_REDIS_GUARD_KEY) != guard_token:
        return False
    await redis_client.delete(_REDIS_GUARD_KEY)
    return await redis_client.dbsize() == 0


async def _create_schema(base_url: str, schema: str) -> None:
    if _SCHEMA_RE.fullmatch(schema) is None:
        raise ValueError('Stress schema name is invalid.')
    connection = await asyncpg.connect(dsn=base_url)
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
    finally:
        await connection.close()


async def _drop_schema(base_url: str, schema: str) -> None:
    if _SCHEMA_RE.fullmatch(schema) is None:
        raise ValueError('Stress schema name is invalid.')
    connection = await asyncpg.connect(dsn=base_url)
    try:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await connection.close()


async def _init_tortoise(schema_url: str, schema: str) -> None:
    await Tortoise.init(
        config={
            'connections': stress_database_connections(schema_url),
            'apps': {'models': {'models': ['app.orm'], 'default_connection': DEFAULT_DB_CONNECTION}},
        }
    )
    for connection_name in (
        DEFAULT_DB_CONNECTION,
        SYSTEM_CACHE_RETENTION_DB_CONNECTION,
        SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    ):
        connection = connections.get(connection_name)
        rows = await connection.execute_query_dict('SELECT current_schema() AS schema')
        active_schema = rows[0].get('schema') if rows else None
        if active_schema != schema:
            raise RuntimeError(f'Stress PostgreSQL search path is not isolated for {connection_name}: {active_schema!r}.')
    await Tortoise.generate_schemas(safe=False)
    connection = connections.get(DEFAULT_DB_CONNECTION)
    await connection.execute_script(
        'ALTER TABLE system_cache_payload SET UNLOGGED; ALTER TABLE system_cache_payload_lease SET UNLOGGED;'
    )
    rows = await connection.execute_query_dict(
        """
        SELECT
            relation.relpersistence,
            EXISTS (
                SELECT 1
                FROM pg_constraint AS constraint_row
                WHERE constraint_row.conrelid = relation.oid
                  AND constraint_row.conname = 'chk_system_cache_payload_size'
            ) AS has_payload_size_check,
            EXISTS (
                SELECT 1
                FROM pg_constraint AS constraint_row
                WHERE constraint_row.conrelid = relation.oid
                  AND constraint_row.conname = 'chk_system_cache_stored_size'
            ) AS has_stored_size_check
        FROM pg_class AS relation
        WHERE relation.oid = to_regclass('system_cache_payload')
        """
    )
    persistence = rows[0].get('relpersistence') if rows else None
    if isinstance(persistence, bytes):
        persistence = persistence.decode()
    if persistence != 'u':
        raise RuntimeError('Stress System Cache payload table is not UNLOGGED.')
    if rows[0].get('has_payload_size_check') is not True:
        raise RuntimeError('Stress System Cache payload table has no payload size constraint.')
    if rows[0].get('has_stored_size_check') is not True:
        raise RuntimeError('Stress System Cache payload table has no stored size constraint.')


class _LoadedManager:
    def __init__(self, manager: SystemJsonRpcCacheManager, loader: JsonRpcLoader) -> None:
        self._manager = manager
        self._loader = loader

    async def get_result(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> bytes | JsonRpcForwardingResult | None:
        return await self._manager.get_result(chain=chain, network=network, call=call, loader=self._loader)


def _manager(
    store: RedisTtlStore,
    loader: JsonRpcLoader,
    policies: SystemJsonRpcCachePolicy,
    redis_client: Redis,
    *,
    flight_wait_seconds: float = 5,
) -> _LoadedManager:
    manager = SystemJsonRpcCacheManager.create(
        store,
        policies,
        RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS),
        flight_wait_seconds=flight_wait_seconds,
    )
    return _LoadedManager(manager, loader)


class UtxoHashLoader:
    def __init__(self) -> None:
        self.calls = 0

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del chain, network
        self.calls += 1
        height = call.params[0] if isinstance(call.params, list) and call.params else 0
        result = f'{height:064x}' if isinstance(height, int) else '0' * 64
        response = JsonRpcSuccessResponse(jsonrpc='2.0', id=call.request_id(), result=orjson.dumps(result))
        return JsonRpcForwardingSuccess(response=response)


class ProtocolWorkloadLoader:
    def __init__(self, *, payload_bytes: int) -> None:
        self._payload_bytes = payload_bytes
        self.calls = 0
        self.calls_by_method: dict[str, int] = {}

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del network
        self.calls += 1
        self.calls_by_method[call.method] = self.calls_by_method.get(call.method, 0) + 1
        await asyncio.sleep(0.02)
        if call.method == 'eth_blockNumber':
            result: object = hex(20_000)
        elif call.method == 'getSlot':
            result = 30_000
        elif call.method == 'getblockchaininfo':
            result = {'blocks': 900_000}
        elif call.method == 'getblockhash':
            height = call.params[0] if isinstance(call.params, list) and call.params else 0
            result = f'{height:064x}' if isinstance(height, int) else '0' * 64
        elif call.method == 'getBlock':
            slot = call.params[0] if isinstance(call.params, list) and call.params else 0
            result = {
                'blockHeight': max(0, slot - 1) if isinstance(slot, int) else 0,
                'blob': 'x' * self._payload_bytes,
            }
        elif call.method == 'getblock':
            block_hash = call.params[0] if isinstance(call.params, list) and call.params else ''
            try:
                height = int(block_hash, 16) if isinstance(block_hash, str) else 0
            except ValueError:
                height = 0
            result = {
                'height': height,
                'hash': block_hash,
                'blob': 'x' * self._payload_bytes,
            }
        else:
            result = {
                'chain': chain.value,
                'method': call.method,
                'blob': 'x' * self._payload_bytes,
            }
        response = JsonRpcSuccessResponse(jsonrpc='2.0', id=call.request_id(), result=orjson.dumps(result))
        return JsonRpcForwardingSuccess(response=response)


async def stress_protocol_workload(
    redis_client: Redis,
    retention_seconds: Mapping[Chain, int],
    *,
    payload_bytes: int,
) -> ScenarioReport:
    started_at = time.monotonic()
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
    loader = ProtocolWorkloadLoader(payload_bytes=min(payload_bytes, 256 * 1024))
    cache_manager = SystemJsonRpcCacheManager.create(
        HybridSystemCacheStore(RedisTtlStore(redis_client), PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)),
        policies,
        RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS),
        postgres_flight=PostgresRetentionFlight(
            lease_ms=FLIGHT_LEASE_MS,
            connection_name=SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
        ),
        flight_wait_seconds=5,
    )
    manager = _LoadedManager(cache_manager, loader)
    heads = (
        (Chain.POLYGON, Network.MAINNET, JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])),
        (
            Chain.SOLANA,
            Network.MAINNET_BETA,
            JsonRpcCall(jsonrpc='2.0', id=2, method='getSlot', params=[{'commitment': 'finalized'}]),
        ),
        (
            Chain.BITCOIN,
            Network.MAINNET,
            JsonRpcCall(jsonrpc='2.0', id=3, method='getblockchaininfo', params=[]),
        ),
    )
    head_results = [await manager.get_result(chain=chain, network=network, call=call) for chain, network, call in heads]
    calls: list[tuple[Chain, Network, JsonRpcCall]] = []
    for offset in range(4):
        calls.append(
            (
                Chain.POLYGON,
                Network.MAINNET,
                JsonRpcCall(
                    jsonrpc='2.0',
                    id=100 + offset,
                    method='debug_traceBlockByNumber',
                    params=[
                        hex(19_900 + offset),
                        {'tracer': 'callTracer', 'tracerConfig': {'withLog': True}},
                    ],
                ),
            )
        )
        calls.append(
            (
                Chain.SOLANA,
                Network.MAINNET_BETA,
                JsonRpcCall(
                    jsonrpc='2.0',
                    id=200 + offset,
                    method='getBlock',
                    params=[29_900 + offset, {'encoding': 'json', 'rewards': False, 'commitment': 'finalized'}],
                ),
            )
        )
        hash_call = JsonRpcCall(jsonrpc='2.0', id=300 + offset, method='getblockhash', params=[899_900 + offset])
        hash_payload = await manager.get_result(chain=Chain.BITCOIN, network=Network.MAINNET, call=hash_call)
        if not isinstance(hash_payload, bytes):
            continue
        block_hash = orjson.loads(hash_payload)
        if isinstance(block_hash, str):
            calls.append(
                (
                    Chain.BITCOIN,
                    Network.MAINNET,
                    JsonRpcCall(jsonrpc='2.0', id=400 + offset, method='getblock', params=[block_hash, 3]),
                )
            )
    request_specs = [(chain, network, call) for chain, network, call in calls for _duplicate in range(2)]
    results = await asyncio.gather(
        *(manager.get_result(chain=chain, network=network, call=call) for chain, network, call in request_specs)
    )
    connection = connections.get(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    rows = await connection.execute_query_dict(
        """
        SELECT chain, operation, COUNT(*)::bigint AS count
        FROM system_cache_payload
        WHERE operation IN ('debug_traceBlockByNumber', 'getBlock', 'getblock')
        GROUP BY chain, operation
        """
    )
    stored = {(row.get('chain'), row.get('operation')): row.get('count') for row in rows}
    returned_by_chain = {
        chain: sum(
            payload is not None
            for (request_chain, _network, _call), payload in zip(request_specs, results, strict=True)
            if request_chain is chain
        )
        for chain in (Chain.POLYGON, Chain.SOLANA, Chain.BITCOIN)
    }
    checks = {
        'heads_returned': all(payload is not None for payload in head_results),
        'all_retention_results_returned': len(results) == 24 and all(payload is not None for payload in results),
        'one_load_per_unique_call': loader.calls == 19,
        'evm_trace_rows_stored': stored.get((Chain.POLYGON.value, 'debug_traceBlockByNumber')) == 4,
        'solana_block_rows_stored': stored.get((Chain.SOLANA.value, 'getBlock')) == 4,
        'bitcoin_block_rows_stored': stored.get((Chain.BITCOIN.value, 'getblock')) == 4,
    }
    return ScenarioReport(
        name='integrated_protocol_scan_workload',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'head_requests': len(heads),
            'retention_requests': len(results),
            'unique_retention_calls': len(calls),
            'upstream_loads': loader.calls,
            'evm_returned': returned_by_chain[Chain.POLYGON],
            'solana_returned': returned_by_chain[Chain.SOLANA],
            'bitcoin_returned': returned_by_chain[Chain.BITCOIN],
            'evm_trace_loads': loader.calls_by_method.get('debug_traceBlockByNumber', 0),
            'solana_block_loads': loader.calls_by_method.get('getBlock', 0),
            'bitcoin_hash_loads': loader.calls_by_method.get('getblockhash', 0),
            'bitcoin_block_loads': loader.calls_by_method.get('getblock', 0),
        },
    )


async def stress_redis(
    redis_client: Redis,
    retention_seconds: Mapping[Chain, int],
    *,
    concurrency: int,
) -> ScenarioReport:
    started_at = time.monotonic()
    store = RedisTtlStore(redis_client)
    loader = CountingLoader(delay_seconds=1.2)
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
    managers = (_manager(store, loader, policies, redis_client), _manager(store, loader, policies, redis_client))
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    results = await asyncio.gather(
        *(
            managers[offset % 2].get_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
            for offset in range(concurrency)
        )
    )
    policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    if policy is None:
        raise RuntimeError('Stress Redis TTL policy is unavailable.')
    now = datetime.now(UTC)
    ttl_entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"ttl"',
        fresh_until=now + timedelta(milliseconds=25),
        stale_until=now + timedelta(milliseconds=75),
        sequence=None,
    )
    ttl_flight = RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS)
    ttl_lease = await ttl_flight.acquire(policy.key)
    if ttl_lease is None:
        raise RuntimeError('Stress Redis TTL lease is unavailable.')
    try:
        if not await store.commit(ttl_entry, ttl_lease, refresh=False):
            raise RuntimeError('Stress Redis TTL commit was fenced.')
    finally:
        await ttl_flight.release(policy.key, ttl_lease)
    ttl_immediate = await store.get(policy)
    await asyncio.sleep(0.12)
    ttl_expired = await store.get(policy)
    checks = {
        'all_results_equal': len(set(results)) == 1 and results[0] is not None,
        'one_cross_process_load': loader.calls == 1,
        'one_active_loader': loader.peak_active == 1,
        'redis_ttl_immediately_available': ttl_immediate is not None,
        'redis_ttl_expires': ttl_expired is None,
    }
    return ScenarioReport(
        name='redis_distributed_singleflight_and_ttl',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'concurrency': concurrency, 'loads': loader.calls, 'peak_active': loader.peak_active},
    )


async def stress_hash_retention(
    redis_client: Redis,
    retention_seconds: Mapping[Chain, int],
    *,
    namespace: str,
) -> ScenarioReport:
    started_at = time.monotonic()
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
    head = 900_000
    store = RedisTtlStore(redis_client)
    loader = UtxoHashLoader()
    cache_manager = SystemJsonRpcCacheManager.create(
        store,
        policies,
        RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS),
        flight_wait_seconds=1,
    )
    manager = _LoadedManager(cache_manager, loader)
    older_call = JsonRpcCall(jsonrpc='2.0', id=2, method='getblockhash', params=[head - 10])
    head_call = JsonRpcCall(jsonrpc='2.0', id=3, method='getblockhash', params=[head])
    older_result = await manager.get_result(chain=Chain.BITCOIN, network=Network.MAINNET, call=older_call)
    head_result = await manager.get_result(chain=Chain.BITCOIN, network=Network.MAINNET, call=head_call)
    pattern = f'{namespace}:system_cache:v1:redis_ttl:jsonrpc:bitcoin:mainnet:getblockhash:*'
    keys = [str(key) async for key in redis_client.scan_iter(match=pattern, count=32)]
    ttls = sorted([await redis_client.pttl(key) for key in keys])
    retention_floor = retention_seconds[Chain.BITCOIN] * 1000
    maximum_ttl = ttls[-1] if ttls else -1
    minimum_ttl = ttls[0] if ttls else -1
    checks = {
        'both_hashes_returned': older_result is not None and head_result is not None,
        'one_load_per_height': loader.calls == 2,
        'two_small_results_stored': len(keys) == 2,
        'all_hashes_use_retention': retention_floor <= minimum_ttl <= maximum_ttl <= retention_floor + 6000,
    }
    return ScenarioReport(
        name='redis_hash_retention',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'loads': loader.calls, 'keys': len(keys), 'minimum_ttl_ms': minimum_ttl, 'maximum_ttl_ms': maximum_ttl},
    )


async def stress_dead_owner(
    redis_client: Redis,
    retention_seconds: Mapping[Chain, int],
) -> ScenarioReport:
    started_at = time.monotonic()
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    if policy is None:
        raise RuntimeError('Stress dead-owner policy is unavailable.')
    owner_flight = RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS)
    token = await owner_flight.acquire(policy.key)
    if token is None:
        raise RuntimeError('Stress dead-owner lease was not acquired.')
    loader = CountingLoader(delay_seconds=0)
    manager = _manager(RedisTtlStore(redis_client), loader, policies, redis_client, flight_wait_seconds=5)
    wait_started = time.monotonic()
    try:
        result = await manager.get_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    finally:
        await owner_flight.release(policy.key, token)
    waited_ms = round((time.monotonic() - wait_started) * 1000)
    checks = {
        'follower_took_over': result is not None,
        'one_takeover_load': loader.calls == 1,
        'wait_bounded': 800 <= waited_ms <= 2500,
    }
    return ScenarioReport(
        name='redis_dead_owner_takeover',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'waited_ms': waited_ms, 'loads': loader.calls},
    )


async def stress_late_owner_fence(
    redis_client: Redis,
    retention_seconds: Mapping[Chain, int],
) -> ScenarioReport:
    """Prove each cache store rejects publishers that no longer own its authoritative lease."""
    started_at = time.monotonic()
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=1000, postgres_retention_seconds=retention_seconds)
    redis_ttl_call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    redis_ttl_policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=redis_ttl_call)
    postgres_call = JsonRpcCall(jsonrpc='2.0', id=2, method='eth_getBlockByNumber', params=['0x64', False])
    postgres_policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=postgres_call)
    if redis_ttl_policy is None or postgres_policy is None:
        raise RuntimeError('Stress late-owner policies are unavailable.')

    redis_ttl_flight = RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS)
    old_redis_ttl_lease = await redis_ttl_flight.acquire(redis_ttl_policy.key)
    if old_redis_ttl_lease is None:
        raise RuntimeError('Stress old Redis TTL lease was not acquired.')
    await redis_client.delete(flight_key(redis_ttl_policy.key))
    new_redis_ttl_lease = await redis_ttl_flight.acquire(redis_ttl_policy.key)
    if new_redis_ttl_lease is None:
        raise RuntimeError('Stress new Redis TTL lease was not acquired.')
    now = datetime.now(UTC)
    redis_ttl_store = RedisTtlStore(redis_client)
    old_redis_ttl_entry = CacheEntry(
        key=redis_ttl_policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"old"',
        fresh_until=now + timedelta(seconds=1),
        stale_until=now + timedelta(seconds=2),
        sequence=None,
    )
    new_redis_ttl_entry = CacheEntry(
        key=redis_ttl_policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"new"',
        fresh_until=now + timedelta(seconds=1),
        stale_until=now + timedelta(seconds=2),
        sequence=None,
    )
    new_redis_ttl_applied = await redis_ttl_store.commit(new_redis_ttl_entry, new_redis_ttl_lease, refresh=False)
    old_redis_ttl_rejected = not await redis_ttl_store.commit(
        old_redis_ttl_entry,
        old_redis_ttl_lease,
        refresh=False,
    )
    saved_redis_ttl_entry = await redis_ttl_store.get(redis_ttl_policy)
    await redis_ttl_flight.release(redis_ttl_policy.key, new_redis_ttl_lease)

    postgres_flight = PostgresRetentionFlight(
        lease_ms=FLIGHT_LEASE_MS,
        connection_name=SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    )
    old_postgres_lease = await postgres_flight.acquire(postgres_policy.key)
    if old_postgres_lease is None:
        raise RuntimeError('Stress old PostgreSQL retention lease was not acquired.')
    await postgres_flight.release(postgres_policy.key, old_postgres_lease)
    new_postgres_lease = await postgres_flight.acquire(postgres_policy.key)
    if new_postgres_lease is None:
        raise RuntimeError('Stress new PostgreSQL retention lease was not acquired.')
    retention_store = PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    old_retained_entry = CacheEntry(
        key=postgres_policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=b'{"number":"0x64","hash":"old"}',
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )
    new_retained_entry = CacheEntry(
        key=postgres_policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=b'{"number":"0x64","hash":"new"}',
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )
    old_postgres_rejected = not await retention_store.commit(old_retained_entry, old_postgres_lease, refresh=False)
    postgres_clean_before_owner_commit = await retention_store.get(postgres_policy) is None
    new_postgres_applied = await retention_store.commit(new_retained_entry, new_postgres_lease, refresh=False)
    saved_retained_entry = await retention_store.get(postgres_policy)
    await postgres_flight.release(postgres_policy.key, new_postgres_lease)
    checks = {
        'redis_ttl_fence_advanced': new_redis_ttl_lease.fence > old_redis_ttl_lease.fence,
        'new_redis_ttl_applied': new_redis_ttl_applied,
        'old_redis_ttl_rejected': old_redis_ttl_rejected,
        'new_redis_ttl_preserved': (
            saved_redis_ttl_entry is not None and saved_redis_ttl_entry.payload == new_redis_ttl_entry.payload
        ),
        'postgres_retention_fence_advanced': new_postgres_lease.fence > old_postgres_lease.fence,
        'postgres_retention_clean_before_owner_commit': postgres_clean_before_owner_commit,
        'new_postgres_retention_applied': new_postgres_applied,
        'old_postgres_retention_rejected': old_postgres_rejected,
        'new_postgres_retention_preserved': (
            saved_retained_entry is not None and saved_retained_entry.payload == new_retained_entry.payload
        ),
    }
    return ScenarioReport(
        name='late_owner_commit_fencing',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'redis_ttl_old_fence': old_redis_ttl_lease.fence,
            'redis_ttl_new_fence': new_redis_ttl_lease.fence,
            'postgres_retention_old_fence': old_postgres_lease.fence,
            'postgres_retention_new_fence': new_postgres_lease.fence,
        },
    )


def _payload_entry(
    index: int,
    payload: bytes,
    *,
    chain: Chain = Chain.ETHEREUM,
    method: str = 'stress_payload',
) -> CacheEntry:
    return CacheEntry(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=chain,
            network=Network.MAINNET,
            operation=method,
            digest=f'{index:040x}',
        ),
        tier=CacheTier.POSTGRES_RETENTION,
        payload=payload,
        fresh_until=None,
        stale_until=None,
        sequence=index,
    )


async def stress_postgres(
    retention_seconds: Mapping[Chain, int],
    *,
    rows: int,
    payload_bytes: int,
    concurrency: int,
) -> ScenarioReport:
    started_at = time.monotonic()
    store = PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])
    policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    if policy is None:
        raise RuntimeError('Stress payload policy is unavailable.')
    payload = b'{"blob":"' + b'x' * max(1, payload_bytes - 11) + b'"}'
    same_entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=payload,
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )
    flight = PostgresRetentionFlight(
        lease_ms=FLIGHT_LEASE_MS,
        connection_name=SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    )

    async def commit(entry: CacheEntry, *, refresh: bool = False) -> bool:
        lease = await flight.acquire(entry.key)
        if lease is None:
            return False
        try:
            return await store.commit(entry, lease, refresh=refresh)
        finally:
            await flight.release(entry.key, lease)

    await asyncio.gather(*(commit(same_entry) for _ in range(concurrency)))
    connection = connections.get(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    same_rows = await connection.execute_query_dict(
        'SELECT COUNT(*)::bigint AS count FROM system_cache_payload WHERE operation = $1',
        [same_entry.key.operation],
    )
    immediate = await store.get(policy)
    retention = retention_seconds[Chain.ETHEREUM]
    await connection.execute_query(
        "UPDATE system_cache_payload SET stored_at = NOW() - ($1::bigint * INTERVAL '1 second') WHERE operation = $2",
        [retention + 1, same_entry.key.operation],
    )
    expired = await store.get(policy)
    if not await commit(same_entry):
        raise RuntimeError('Stress Payload replacement commit was fenced.')
    before_refresh = await connection.execute_query_dict(
        'SELECT stored_at FROM system_cache_payload WHERE operation = $1',
        [same_entry.key.operation],
    )
    refreshed = CacheEntry(
        key=same_entry.key,
        tier=same_entry.tier,
        payload=same_entry.payload,
        fresh_until=datetime.now(UTC) + timedelta(seconds=1),
        stale_until=datetime.now(UTC) + timedelta(seconds=2),
        sequence=same_entry.sequence,
    )
    if not await commit(refreshed, refresh=True):
        raise RuntimeError('Stress Payload refresh commit was fenced.')
    after_refresh = await connection.execute_query_dict(
        'SELECT stored_at FROM system_cache_payload WHERE operation = $1',
        [same_entry.key.operation],
    )
    cleanup_payload = b'{"stress":true}'
    chains = tuple(Chain)
    entries = [_payload_entry(index + 1000, cleanup_payload, chain=chains[index % len(chains)]) for index in range(rows)]
    for offset in range(0, len(entries), concurrency):
        results = await asyncio.gather(*(commit(entry) for entry in entries[offset : offset + concurrency]))
        if not all(results):
            raise RuntimeError('Stress Payload seed commit was fenced.')
    await connection.execute_query(
        "UPDATE system_cache_payload SET stored_at = NOW() - INTERVAL '8 days' WHERE operation = 'stress_payload'"
    )
    max_cleanup_bytes = CONF.SYSTEM_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES
    first, second = await asyncio.gather(
        store.delete_expired(Chain.ETHEREUM, retention_seconds[Chain.ETHEREUM], max_rows=64, max_bytes=max_cleanup_bytes),
        store.delete_expired(Chain.ETHEREUM, retention_seconds[Chain.ETHEREUM], max_rows=64, max_bytes=max_cleanup_bytes),
    )
    deleted_rows = first.deleted_rows + second.deleted_rows
    for chain in chains:
        while True:
            batch = await store.delete_expired(
                chain,
                retention_seconds[chain],
                max_rows=64,
                max_bytes=max_cleanup_bytes,
            )
            deleted_rows += batch.deleted_rows
            if not batch.has_more:
                break
    invariants = await connection.execute_query_dict(
        """
        SELECT
            COUNT(*) FILTER (WHERE payload_size < 0 OR stored_size <> octet_length(payload))::bigint AS invalid_sizes,
            COUNT(*) FILTER (WHERE operation = 'stress_payload')::bigint AS expired_rows,
            COUNT(*) FILTER (WHERE operation = $1)::bigint AS live_rows
        FROM system_cache_payload
        """,
        [same_entry.key.operation],
    )
    row = invariants[0]
    checks = {
        'concurrent_upsert_is_unique': bool(same_rows) and same_rows[0].get('count') == 1,
        'immediate_hit': immediate is not None,
        'expired_read_misses': expired is None,
        'refresh_is_not_sliding': bool(before_refresh)
        and bool(after_refresh)
        and before_refresh[0].get('stored_at') == after_refresh[0].get('stored_at'),
        'concurrent_cleanup_bounded': first.deleted_rows <= 64 and second.deleted_rows <= 64,
        'all_expired_rows_deleted': row.get('expired_rows') == 0 and deleted_rows == rows,
        'payload_sizes_valid': row.get('invalid_sizes') == 0,
        'live_row_preserved': row.get('live_rows') == 1,
    }
    return ScenarioReport(
        name='postgres_time_retention_and_concurrency',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'concurrency': concurrency,
            'seed_rows': rows,
            'deleted_rows': deleted_rows,
            'payload_bytes': len(payload),
        },
    )


async def stress_postgres_pool_isolation(retention_seconds: Mapping[Chain, int]) -> ScenarioReport:
    started_at = time.monotonic()
    policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x7b', False])
    policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    if policy is None:
        raise RuntimeError('Stress pool isolation policy is unavailable.')

    retention_connection = connections.get(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    retention_store = PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    coordination = PostgresRetentionFlight(
        lease_ms=5000,
        io_timeout_seconds=0.25,
        connection_name=SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    )
    retention_read: asyncio.Task[CacheEntry | None] | None = None
    acquired = False
    renewed = False
    released = False
    reacquired = False
    coordination_elapsed_ms = 0
    async with AsyncExitStack() as stack:
        for _index in range(STRESS_DB_POOL_MAX_SIZE):
            await stack.enter_async_context(retention_connection.acquire_connection())
        retention_read = asyncio.create_task(retention_store.get(policy))
        await asyncio.sleep(0.05)
        retention_pool_saturated = not retention_read.done()

        coordination_started_at = time.monotonic()
        lease = None
        replacement_lease = None
        try:
            lease = await coordination.acquire(policy.key)
            acquired = lease is not None
            if lease is not None:
                renewed = await coordination.renew(policy.key, lease)
                await coordination.release(policy.key, lease)
                replacement_lease = await coordination.acquire(policy.key)
                released = replacement_lease is not None
                reacquired = replacement_lease is not None and replacement_lease.fence > lease.fence
        except TimeoutError:
            pass
        finally:
            coordination_elapsed_ms = round((time.monotonic() - coordination_started_at) * 1000)
            if replacement_lease is not None:
                await coordination.release(policy.key, replacement_lease)
            elif lease is not None and not released:
                with suppress(TimeoutError):
                    await coordination.release(policy.key, lease)

        retention_read.cancel()
        with suppress(asyncio.CancelledError):
            await retention_read

    checks = {
        'retention_pool_saturated': retention_pool_saturated,
        'coordination_acquired_while_retention_saturated': acquired,
        'coordination_heartbeat_succeeded_while_retention_saturated': renewed,
        'coordination_release_succeeded_while_retention_saturated': released,
        'coordination_fence_advanced_after_release': reacquired,
        'coordination_operations_remained_bounded': coordination_elapsed_ms <= 1000,
    }
    return ScenarioReport(
        name='postgres_retention_and_coordination_pool_isolation',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'retention_pool_size': STRESS_DB_POOL_MAX_SIZE,
            'coordination_elapsed_ms': coordination_elapsed_ms,
        },
    )


async def run_integration(
    redis_url: str,
    postgres_url: str,
    retention_seconds: Mapping[Chain, int],
    *,
    concurrency: int,
    rows: int,
    payload_bytes: int,
) -> tuple[list[ScenarioReport], dict[str, object]]:
    redis_host, redis_port, redis_db = _redis_target(redis_url)
    schema = f'rpc_cache_stress_{secrets.token_hex(16)}'
    base_url, schema_url, database = _postgres_urls(postgres_url, schema)
    redis_client = Redis.from_url(redis_url, decode_responses=True, retry_on_timeout=False)
    guard_token: str | None = None
    namespace = f'{CONF.PROJECT_NAME}-system-cache-stress-{secrets.token_hex(6)}'
    saved_project_name = CONF.PROJECT_NAME
    schema_created = False
    redis_clean = False
    cleanup_errors: list[str] = []
    try:
        guard_token = await _prepare_redis(redis_client)
        CONF.PROJECT_NAME = namespace
        await _create_schema(base_url, schema)
        schema_created = True
        await _init_tortoise(schema_url, schema)
        reports = [
            await stress_redis(redis_client, retention_seconds, concurrency=concurrency),
            await stress_hash_retention(redis_client, retention_seconds, namespace=namespace),
            await stress_dead_owner(redis_client, retention_seconds),
            await stress_late_owner_fence(redis_client, retention_seconds),
            await stress_protocol_workload(redis_client, retention_seconds, payload_bytes=payload_bytes),
            await stress_postgres(
                retention_seconds,
                rows=rows,
                payload_bytes=payload_bytes,
                concurrency=concurrency,
            ),
            await stress_postgres_pool_isolation(retention_seconds),
            await stress_postgres_retention_workload(
                redis_client,
                redis_url,
                schema_url,
                namespace,
                retention_seconds,
                shape=WorkloadShape(
                    workers=4,
                    blocks=32 if payload_bytes >= 1024 * 1024 else 8,
                    payload_bytes=payload_bytes,
                ),
            ),
        ]
        return reports, {
            'redis': {'host': redis_host, 'port': redis_port, 'db': redis_db},
            'postgres_database': database,
            'schema_isolated': True,
            'redis_clean': True,
        }
    finally:
        try:
            await Tortoise.close_connections()
        except Exception as exc:
            cleanup_errors.append(f'Tortoise close failed: {exc!r}')
        if schema_created:
            try:
                await _drop_schema(base_url, schema)
            except Exception as exc:
                cleanup_errors.append(f'PostgreSQL schema cleanup failed: {exc!r}')
        CONF.PROJECT_NAME = saved_project_name
        if guard_token is not None:
            try:
                redis_clean = await _cleanup_redis(redis_client, guard_token=guard_token, namespace=namespace)
            except Exception as exc:
                cleanup_errors.append(f'Redis key cleanup failed: {exc!r}')
        try:
            await redis_client.aclose()
        except Exception as exc:
            cleanup_errors.append(f'Redis close failed: {exc!r}')
        if guard_token is not None and not redis_clean:
            cleanup_errors.append('Stress Redis cleanup did not restore an empty dedicated database.')
        if cleanup_errors:
            raise RuntimeError('; '.join(cleanup_errors))
