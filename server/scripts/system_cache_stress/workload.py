import asyncio
import hashlib
import multiprocessing
import os
import queue
import time
from collections.abc import Mapping
from dataclasses import dataclass
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Barrier

import orjson
from app.core.config import CONF
from app.infra.db import (
    DEFAULT_DB_CONNECTION,
    SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    SYSTEM_CACHE_RETENTION_DB_CONNECTION,
)
from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import JsonRpcForwardingSuccess
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.model.system_cache import CacheEntry, CacheFlightLease, CachePolicy
from app.services.system_cache.flight import PostgresRetentionFlight, RedisTtlFlight
from app.services.system_cache.limits import FLIGHT_LEASE_MS
from app.services.system_cache.store import HybridSystemCacheStore, PostgresRetentionStore, RedisTtlStore
from app.services.system_jsonrpc_cache import SystemJsonRpcCacheManager
from app.services.system_jsonrpc_cache.policy import SystemJsonRpcCachePolicy
from redis.asyncio import Redis
from scripts.system_cache_stress.database import stress_database_connections
from scripts.system_cache_stress.report import ScenarioReport
from tortoise import Tortoise, connections


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkloadShape:
    workers: int
    blocks: int
    payload_bytes: int


class CountingHybridStore:
    def __init__(self, redis_client: Redis) -> None:
        self._store = HybridSystemCacheStore(
            RedisTtlStore(redis_client), PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
        )
        self.reads = 0
        self.writes = 0
        self.refreshes = 0

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        self.reads += 1
        return await self._store.get(policy)

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        if refresh:
            self.refreshes += 1
        else:
            self.writes += 1
        return await self._store.commit(entry, lease, refresh=refresh)


class RedisCountingLoader:
    def __init__(self, redis_client: Redis, *, counter_key: str, payload_bytes: int) -> None:
        self._redis = redis_client
        self._counter_key = counter_key
        self._payload_bytes = payload_bytes

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del chain, network
        await self._redis.incr(self._counter_key)
        await asyncio.sleep(1.2)
        height = call.params[0] if isinstance(call.params, list) and call.params else '0x0'
        result = {'number': height, 'blob': 'x' * self._payload_bytes}
        response = JsonRpcSuccessResponse(jsonrpc='2.0', id=call.request_id(), result=orjson.dumps(result))
        return JsonRpcForwardingSuccess(response=response)


def _rss_bytes() -> int:
    with open('/proc/self/statm') as statm:
        resident_pages = int(statm.read().split()[1])
    return resident_pages * os.sysconf('SC_PAGE_SIZE')


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return ordered[index]


async def _run_worker(
    *,
    worker_index: int,
    redis_url: str,
    schema_url: str,
    namespace: str,
    counter_key: str,
    retention_by_name: Mapping[str, int],
    shape: WorkloadShape,
    start_height: int,
) -> dict[str, int | str | bool]:
    CONF.PROJECT_NAME = namespace
    redis_client = Redis.from_url(redis_url, decode_responses=True, retry_on_timeout=False)
    baseline_rss = _rss_bytes()
    peak_rss = baseline_rss
    baseline_tasks = len(asyncio.all_tasks())
    started_at = time.monotonic()
    cpu_started = time.process_time()
    latencies_ms: list[int] = []
    await Tortoise.init(
        config={
            'connections': stress_database_connections(schema_url),
            'apps': {'models': {'models': ['app.orm'], 'default_connection': DEFAULT_DB_CONNECTION}},
        }
    )
    try:
        retention_seconds = {Chain(chain): seconds for chain, seconds in retention_by_name.items()}
        policies = SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)
        store = CountingHybridStore(redis_client)
        loader = RedisCountingLoader(redis_client, counter_key=counter_key, payload_bytes=shape.payload_bytes)
        manager = SystemJsonRpcCacheManager.create(
            store,
            policies,
            RedisTtlFlight(redis_client, lease_ms=FLIGHT_LEASE_MS),
            postgres_flight=PostgresRetentionFlight(
                lease_ms=FLIGHT_LEASE_MS,
                connection_name=SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
            ),
            flight_wait_seconds=5,
        )
        await asyncio.sleep(worker_index * 0.03)
        digest = hashlib.sha256()
        completed = 0
        policy_misses = 0
        store_misses = 0
        unexplained_misses = 0
        for offset in range(shape.blocks):
            height = start_height + offset
            call = JsonRpcCall(
                jsonrpc='2.0',
                id=height,
                method='eth_getBlockByNumber',
                params=[hex(height), False],
            )
            request_started = time.monotonic()
            result = await manager.get_result(
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                call=call,
                loader=loader,
            )
            latencies_ms.append(round((time.monotonic() - request_started) * 1000))
            if result is None:
                policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
                if policy is None:
                    policy_misses += 1
                    continue
                saved = await PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION).get(policy)
                if saved is None:
                    store_misses += 1
                else:
                    unexplained_misses += 1
                continue
            if not isinstance(result, bytes):
                unexplained_misses += 1
                continue
            digest.update(result)
            completed += 1
            peak_rss = max(peak_rss, _rss_bytes())
            await asyncio.sleep(0.005)
        await asyncio.sleep(0)
        final_tasks = len(asyncio.all_tasks())
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        cpu_ms = round((time.process_time() - cpu_started) * 1000)
        return {
            'success': completed == shape.blocks and final_tasks <= baseline_tasks,
            'completed': completed,
            'reads': store.reads,
            'writes': store.writes,
            'refreshes': store.refreshes,
            'rss_growth_bytes': max(0, peak_rss - baseline_rss),
            'elapsed_ms': elapsed_ms,
            'cpu_ms': cpu_ms,
            'cpu_percent_milli': round(cpu_ms / elapsed_ms * 100_000) if elapsed_ms else 0,
            'request_p95_ms': _percentile(latencies_ms, 0.95),
            'request_max_ms': max(latencies_ms, default=0),
            'digest': digest.hexdigest(),
            'task_leak': final_tasks > baseline_tasks,
            'policy_misses': policy_misses,
            'store_misses': store_misses,
            'unexplained_misses': unexplained_misses,
        }
    finally:
        await Tortoise.close_connections()
        await redis_client.aclose()


def _worker_entry(
    barrier: Barrier,
    result_queue: Queue,
    worker_index: int,
    redis_url: str,
    schema_url: str,
    namespace: str,
    counter_key: str,
    retention_by_name: Mapping[str, int],
    shape: WorkloadShape,
    start_height: int,
) -> None:
    try:
        barrier.wait(timeout=30)
        result = asyncio.run(
            _run_worker(
                worker_index=worker_index,
                redis_url=redis_url,
                schema_url=schema_url,
                namespace=namespace,
                counter_key=counter_key,
                retention_by_name=retention_by_name,
                shape=shape,
                start_height=start_height,
            )
        )
    except Exception as exc:
        result = {'success': False, 'error': f'{type(exc).__name__}: {exc}'}
    result_queue.put(result)


def _collect_processes(
    *,
    redis_url: str,
    schema_url: str,
    namespace: str,
    counter_key: str,
    retention_by_name: Mapping[str, int],
    shape: WorkloadShape,
    start_height: int,
) -> list[dict[str, object]]:
    context = multiprocessing.get_context('spawn')
    barrier = context.Barrier(shape.workers)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_worker_entry,
            args=(
                barrier,
                result_queue,
                worker_index,
                redis_url,
                schema_url,
                namespace,
                counter_key,
                retention_by_name,
                shape,
                start_height,
            ),
        )
        for worker_index in range(shape.workers)
    ]
    try:
        for process in processes:
            process.start()
        results: list[dict[str, object]] = []
        for _process in processes:
            try:
                results.append(result_queue.get(timeout=180))
            except queue.Empty:
                results.append({'success': False, 'error': 'Worker result timed out.'})
        for process in processes:
            process.join(timeout=10)
        return results
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        result_queue.close()


async def stress_postgres_retention_workload(
    redis_client: Redis,
    redis_url: str,
    schema_url: str,
    namespace: str,
    retention_seconds: Mapping[Chain, int],
    *,
    shape: WorkloadShape,
) -> ScenarioReport:
    started_at = time.monotonic()
    start_height = 10_000
    counter_key = f'{namespace}:stress:upstream-loads'
    await redis_client.delete(counter_key)
    retention_by_name = {chain.value: seconds for chain, seconds in retention_seconds.items()}
    redis_cpu_before = await redis_client.info('cpu')
    results = await asyncio.to_thread(
        _collect_processes,
        redis_url=redis_url,
        schema_url=schema_url,
        namespace=namespace,
        counter_key=counter_key,
        retention_by_name=retention_by_name,
        shape=shape,
        start_height=start_height,
    )
    redis_cpu_after = await redis_client.info('cpu')
    raw_loads = await redis_client.get(counter_key)
    upstream_loads = int(raw_loads) if isinstance(raw_loads, str | bytes) else 0
    connection = connections.get(SYSTEM_CACHE_RETENTION_DB_CONNECTION)
    rows = await connection.execute_query_dict(
        """
        SELECT COUNT(*)::bigint AS count, COALESCE(SUM(payload_size), 0)::bigint AS payload_bytes
        FROM system_cache_payload
        WHERE operation = 'eth_getBlockByNumber' AND sequence >= $1 AND sequence < $2
        """,
        [start_height, start_height + shape.blocks],
    )
    stored_rows = rows[0].get('count') if rows else 0
    stored_bytes = rows[0].get('payload_bytes') if rows else 0
    successful_workers = sum(result.get('success') is True for result in results)
    worker_completed = [value for result in results if isinstance((value := result.get('completed')), int)]
    completed = sum(value for result in results if isinstance((value := result.get('completed')), int))
    reads = sum(value for result in results if isinstance((value := result.get('reads')), int))
    writes = sum(value for result in results if isinstance((value := result.get('writes')), int))
    policy_misses = sum(value for result in results if isinstance((value := result.get('policy_misses')), int))
    store_misses = sum(value for result in results if isinstance((value := result.get('store_misses')), int))
    unexplained_misses = sum(value for result in results if isinstance((value := result.get('unexplained_misses')), int))
    rss_growth = max(
        (value for result in results if isinstance((value := result.get('rss_growth_bytes')), int)),
        default=0,
    )
    worker_cpu_percent_milli = max(
        (value for result in results if isinstance((value := result.get('cpu_percent_milli')), int)),
        default=0,
    )
    request_p95_ms = max(
        (value for result in results if isinstance((value := result.get('request_p95_ms')), int)),
        default=0,
    )
    request_max_ms = max(
        (value for result in results if isinstance((value := result.get('request_max_ms')), int)),
        default=0,
    )
    redis_cpu_seconds = sum(
        float(redis_cpu_after.get(field, 0)) - float(redis_cpu_before.get(field, 0))
        for field in ('used_cpu_sys', 'used_cpu_user')
    )
    checks = {
        'all_workers_completed': successful_workers == shape.workers,
        'all_requests_returned': completed == shape.workers * shape.blocks,
        'one_upstream_load_per_unique_block': upstream_loads == shape.blocks,
        'one_postgres_row_per_unique_block': stored_rows == shape.blocks,
        'payload_bytes_persisted': isinstance(stored_bytes, int) and stored_bytes >= shape.blocks * shape.payload_bytes,
        'worker_rss_bounded': rss_growth <= 256 * 1024 * 1024,
        'worker_cpu_bounded': worker_cpu_percent_milli <= 85_000,
        'request_p95_bounded': request_p95_ms <= 5000,
    }
    return ScenarioReport(
        name='multiprocess_postgres_retention_workload',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'workers': shape.workers,
            'blocks': shape.blocks,
            'requests': shape.workers * shape.blocks,
            'completed': completed,
            'min_worker_completed': min(worker_completed, default=0),
            'max_worker_completed': max(worker_completed, default=0),
            'upstream_loads': upstream_loads,
            'postgres_reads': reads,
            'postgres_writes': writes,
            'policy_misses': policy_misses,
            'store_misses': store_misses,
            'unexplained_misses': unexplained_misses,
            'stored_rows': stored_rows if isinstance(stored_rows, int) else 0,
            'stored_bytes': stored_bytes if isinstance(stored_bytes, int) else 0,
            'max_worker_rss_growth_bytes': rss_growth,
            'max_worker_cpu_percent_milli': worker_cpu_percent_milli,
            'max_worker_request_p95_ms': request_p95_ms,
            'max_worker_request_ms': request_max_ms,
            'redis_cpu_ms': max(0, round(redis_cpu_seconds * 1000)),
        },
    )
