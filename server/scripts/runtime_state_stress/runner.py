import argparse
import asyncio
import json
import math
import os
import resource
import secrets
import sys
import time
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from app.core.config import CONF
from app.infra import redis
from app.services.runtime_state.endpoint.tip.store import MAX_ENDPOINTS
from redis.asyncio import Redis
from scripts.runtime_state_stress.health_circuit import stress_circuit, stress_health
from scripts.runtime_state_stress.metrics import ResourceMonitor, ScenarioReport, read_redis_snapshot, redis_delta
from scripts.runtime_state_stress.mixed_outage import stress_mixed, stress_outage, stress_page_stall
from scripts.runtime_state_stress.runtime_config import LEASE_SECONDS, RENEW_THRESHOLD_SECONDS
from scripts.runtime_state_stress.scenarios import (
    StressShape,
    stress_chain_tip,
    stress_dispatcher,
    stress_endpoint_store,
    stress_lease_renewal,
)

CLEANUP_BATCH_SIZE: Final[int] = 256
GUARD_KEY: Final[str] = 'runtime-state-stress:guard'


@dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    users: int
    endpoint_count: int
    dispatcher_operations: int
    chain_readers: int
    mixed_seconds: float
    max_rss_mib: float
    max_rss_growth_mib: float
    max_cpu_percent: float
    max_redis_memory_mib: float
    max_redis_cpu_percent: float
    max_task_growth: int
    max_rss_slope_mib_per_minute: float
    max_health_drop_rate: float


PROFILES: Final[dict[str, Profile]] = {
    'quick': Profile(
        users=16,
        endpoint_count=1000,
        dispatcher_operations=10_000,
        chain_readers=64,
        mixed_seconds=3,
        max_rss_mib=256,
        max_rss_growth_mib=96,
        max_cpu_percent=105,
        max_redis_memory_mib=128,
        max_redis_cpu_percent=105,
        max_task_growth=256,
        max_rss_slope_mib_per_minute=64,
        max_health_drop_rate=0.01,
    ),
    'full': Profile(
        users=64,
        endpoint_count=10_000,
        dispatcher_operations=200_000,
        chain_readers=512,
        mixed_seconds=10,
        max_rss_mib=384,
        max_rss_growth_mib=192,
        max_cpu_percent=105,
        max_redis_memory_mib=128,
        max_redis_cpu_percent=105,
        max_task_growth=1024,
        max_rss_slope_mib_per_minute=64,
        max_health_drop_rate=0.01,
    ),
    'soak': Profile(
        users=64,
        endpoint_count=5000,
        dispatcher_operations=100_000,
        chain_readers=256,
        mixed_seconds=300,
        max_rss_mib=384,
        max_rss_growth_mib=192,
        max_cpu_percent=105,
        max_redis_memory_mib=128,
        max_redis_cpu_percent=105,
        max_task_growth=1024,
        max_rss_slope_mib_per_minute=5,
        max_health_drop_rate=0.01,
    ),
}


def _shape(args: argparse.Namespace) -> StressShape:
    profile = PROFILES[args.profile]
    users = args.users or profile.users
    endpoint_count = args.endpoints or profile.endpoint_count
    dispatcher_operations = args.ops or profile.dispatcher_operations
    chain_readers = args.chain_readers or profile.chain_readers
    if endpoint_count < 3 or endpoint_count > MAX_ENDPOINTS:
        raise ValueError(f'Endpoint count must be between 3 and {MAX_ENDPOINTS}.')
    if users > 1024:
        raise ValueError('User count cannot exceed 1024.')
    if chain_readers > 4096:
        raise ValueError('Chain reader count cannot exceed 4096.')
    renewal_seconds = args.renewal_seconds or RENEW_THRESHOLD_SECONDS + 0.5
    if not RENEW_THRESHOLD_SECONDS < renewal_seconds < LEASE_SECONDS:
        raise ValueError('Renewal aggregation duration must be above the Redis I/O threshold and below the derived lease.')
    return StressShape(
        users=users,
        endpoint_count=endpoint_count,
        dispatcher_operations=dispatcher_operations,
        chain_readers=chain_readers,
        renewal_seconds=renewal_seconds,
        mixed_seconds=args.soak_seconds or profile.mixed_seconds,
        soak=args.profile == 'soak',
    )


def _redis_target(url: str) -> dict[str, str | int | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in {'redis', 'rediss'}:
        raise ValueError('Redis URL must use redis:// or rediss://.')
    path = parsed.path.removeprefix('/')
    if not path or not path.isascii() or not path.isdecimal():
        raise ValueError('Redis URL must include an explicit numeric database path.')
    return {
        'scheme': parsed.scheme,
        'host': parsed.hostname,
        'port': parsed.port or 6379,
        'db': int(path),
    }


async def _prepare_database(redis_client: Redis) -> str:
    # Reason: redis.asyncio commands are awaitable at runtime; the ping stub includes a sync branch.
    await redis_client.ping()  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
    token = secrets.token_urlsafe(16)
    acquired = await redis_client.set(GUARD_KEY, token, nx=True)
    if not acquired:
        raise RuntimeError('The dedicated Redis DB is already guarded by another stress runner.')
    guarded_size = await redis_client.dbsize()
    if guarded_size != 1:
        await redis.delete_string_if_value(redis_client, GUARD_KEY, token)
        raise RuntimeError('The stress Redis DB must be dedicated and empty before guard acquisition.')
    return token


async def _cleanup_database(redis_client: Redis, *, guard_token: str) -> dict[str, int | bool]:
    saved_guard = await redis_client.get(GUARD_KEY)
    if saved_guard != guard_token:
        return {'deleted_keys': 0, 'guard_owned': False, 'remaining_keys': int(await redis_client.dbsize())}
    pattern = redis.build_pattern('runtime_state', '*')
    deleted = 0
    keys: list[str] = []
    async for key in redis_client.scan_iter(match=pattern, count=CLEANUP_BATCH_SIZE):
        keys.append(str(key))
        if len(keys) >= CLEANUP_BATCH_SIZE:
            if await redis_client.get(GUARD_KEY) != guard_token:
                return {'deleted_keys': deleted, 'guard_owned': False, 'remaining_keys': int(await redis_client.dbsize())}
            deleted += int(await redis_client.unlink(*keys))
            keys.clear()
    if keys:
        if await redis_client.get(GUARD_KEY) != guard_token:
            return {'deleted_keys': deleted, 'guard_owned': False, 'remaining_keys': int(await redis_client.dbsize())}
        deleted += int(await redis_client.unlink(*keys))
    guard_owned = await redis.delete_string_if_value(redis_client, GUARD_KEY, guard_token)
    deleted += int(guard_owned)
    return {'deleted_keys': deleted, 'guard_owned': guard_owned, 'remaining_keys': int(await redis_client.dbsize())}


async def _key_summary(redis_client: Redis) -> dict[str, object]:
    pattern = redis.build_pattern('runtime_state', '*')
    keys = [str(key) async for key in redis_client.scan_iter(match=pattern, count=CLEANUP_BATCH_SIZE)]
    types: dict[str, int] = {}
    hash_fields = 0
    sorted_set_members = 0
    for offset in range(0, len(keys), CLEANUP_BATCH_SIZE):
        page = keys[offset : offset + CLEANUP_BATCH_SIZE]
        async with redis_client.pipeline(transaction=False) as pipeline:
            for key in page:
                pipeline.type(key)
            page_types = await pipeline.execute()
        hash_keys: list[str] = []
        sorted_set_keys: list[str] = []
        for key, key_type_raw in zip(page, page_types, strict=True):
            key_type = str(key_type_raw)
            types[key_type] = types.get(key_type, 0) + 1
            if key_type == 'hash':
                hash_keys.append(key)
            elif key_type == 'zset':
                sorted_set_keys.append(key)
        async with redis_client.pipeline(transaction=False) as pipeline:
            for key in hash_keys:
                pipeline.hlen(key)
            for key in sorted_set_keys:
                pipeline.zcard(key)
            cardinalities = await pipeline.execute()
        hash_fields += sum(int(value) for value in cardinalities[: len(hash_keys)])
        sorted_set_members += sum(int(value) for value in cardinalities[len(hash_keys) :])
    return {
        'keys': len(keys),
        'types': types,
        'hash_fields': hash_fields,
        'sorted_set_members': sorted_set_members,
    }


def _capacity_limits(args: argparse.Namespace, profile: Profile) -> dict[str, float | int]:
    max_health_drop_rate = args.max_health_drop_rate
    if max_health_drop_rate is None:
        max_health_drop_rate = profile.max_health_drop_rate
    return {
        'max_rss_mib': args.max_rss_mib or profile.max_rss_mib,
        'max_rss_growth_mib': args.max_rss_growth_mib or profile.max_rss_growth_mib,
        'max_cpu_percent': args.max_cpu_percent or profile.max_cpu_percent,
        'max_redis_memory_mib': args.max_redis_memory_mib or profile.max_redis_memory_mib,
        'max_redis_cpu_percent': args.max_redis_cpu_percent or profile.max_redis_cpu_percent,
        'max_task_growth': args.max_task_growth or profile.max_task_growth,
        'max_rss_slope_mib_per_minute': (args.max_rss_slope_mib_per_minute or profile.max_rss_slope_mib_per_minute),
        'max_health_drop_rate': max_health_drop_rate,
    }


def _health_drop_rate(scenarios: list[ScenarioReport]) -> float | None:
    for scenario in scenarios:
        if scenario.name not in {'mixed_extractor_tip_chain', 'mixed_extractor_tip_chain_soak'}:
            continue
        accepted = scenario.counts.get('health_accepted', 0)
        dropped = scenario.counts.get('health_dropped', 0)
        return dropped / accepted if accepted else 0.0
    return None


def _threshold_checks(
    limits: dict[str, float | int],
    resources: dict[str, float | int],
    redis_metrics: dict[str, object],
    *,
    health_drop_rate: float | None,
) -> dict[str, bool]:
    mib = 1024 * 1024
    checks: dict[str, bool] = {}
    sampled_peak = redis_metrics['used_memory_sampled_peak_bytes']
    if not isinstance(sampled_peak, int | float):
        raise RuntimeError('Redis sampled memory metric is invalid.')
    checks['max_rss_mib'] = int(resources['rss_peak_bytes']) <= float(limits['max_rss_mib']) * mib
    checks['max_rss_growth_mib'] = int(resources['rss_growth_bytes']) <= float(limits['max_rss_growth_mib']) * mib
    checks['max_cpu_percent'] = float(resources['process_cpu_peak_percent_one_core']) <= float(limits['max_cpu_percent'])
    checks['max_redis_memory_mib'] = sampled_peak <= float(limits['max_redis_memory_mib']) * mib
    checks['max_redis_cpu_percent'] = float(resources['redis_cpu_peak_percent_one_core']) <= float(
        limits['max_redis_cpu_percent']
    )
    growth = int(resources['asyncio_tasks_peak']) - int(resources['asyncio_tasks_baseline'])
    checks['max_task_growth'] = growth <= int(limits['max_task_growth'])
    checks['max_rss_slope_mib_per_minute'] = (
        float(resources['rss_slope_bytes_per_minute']) <= float(limits['max_rss_slope_mib_per_minute']) * mib
    )
    checks['max_health_drop_rate'] = health_drop_rate is not None and health_drop_rate <= float(limits['max_health_drop_rate'])
    return checks


def _redis_client(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        retry_on_timeout=False,
        socket_connect_timeout=CONF.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=CONF.REDIS_SOCKET_TIMEOUT_SECONDS,
    )


async def _run(args: argparse.Namespace) -> tuple[dict[str, object], bool]:
    shape = _shape(args)
    redis_url = args.redis_url or os.getenv('RUNTIME_STATE_STRESS_REDIS_URL')
    if not redis_url:
        raise ValueError('Provide --redis-url or RUNTIME_STATE_STRESS_REDIS_URL.')
    target = _redis_target(redis_url)
    outage_target = _redis_target(args.outage_redis_url)
    if outage_target == target:
        raise ValueError('The outage Redis target must not be the dedicated stress Redis target.')
    redis_client = _redis_client(redis_url)
    profile = PROFILES[args.profile]
    limits = _capacity_limits(args, profile)
    guard_token: str | None = None
    cleanup: dict[str, int | bool] = {}
    report: dict[str, object] = {
        'profile': args.profile,
        'shape': {
            'users': shape.users,
            'endpoint_count': shape.endpoint_count,
            'dispatcher_operations': shape.dispatcher_operations,
            'chain_readers': shape.chain_readers,
            'renewal_seconds': shape.renewal_seconds,
            'mixed_seconds': shape.mixed_seconds,
            'soak': shape.soak,
        },
        'capacity_limits': limits,
        'redis_target': target,
        'outage_target': outage_target,
        'namespace': [f'{CONF.PROJECT_NAME}:runtime_state:v2', f'{CONF.PROJECT_NAME}:runtime_state:v3'],
        'scenarios': [],
        'errors': [],
        'coverage': {
            'endpoint_state': ['health shared window', 'tip observation store', 'tip dispatcher'],
            'chain_state': ['trusted chain tip aggregation', 'lease renewal', 'synthetic no-yield page boundary'],
            'circuit_breaker': [
                'closed/open/half-open transitions',
                'shared probe',
                'version isolation',
                'workload isolation',
                'sampled failure window',
            ],
            'combined': [
                'circuit admission and result',
                'health batching',
                'extractor to tip dispatcher',
                'concurrent paging and chain aggregation',
            ],
            'failure_modes': ['real Redis connection outage', 'bounded retry age/count/tasks'],
        },
    }
    success = False
    try:
        guard_token = await _prepare_database(redis_client)
        baseline_tasks = len(asyncio.all_tasks())
        redis_start = await read_redis_snapshot(redis_client)
        monitor = ResourceMonitor(
            redis_client=redis_client,
            sample_interval=args.sample_interval,
            baseline_tasks=baseline_tasks,
        )
        wall_started = time.monotonic()
        cpu_started = time.process_time()
        monitor.redis_peak = redis_start.used_memory
        monitor.start()
        scenario_functions = (
            lambda: stress_health(redis_client, shape),
            lambda: stress_circuit(redis_client, shape),
            lambda: stress_dispatcher(redis_client, shape),
            lambda: stress_endpoint_store(redis_client, shape),
            lambda: stress_chain_tip(redis_client, shape),
            lambda: stress_mixed(redis_client, shape),
            lambda: stress_lease_renewal(redis_client, shape),
            lambda: stress_page_stall(redis_client, stall_seconds=shape.renewal_seconds),
            lambda: stress_outage(args.outage_redis_url),
        )
        scenarios: list[ScenarioReport] = []
        errors: list[str] = []
        for scenario_function in scenario_functions:
            try:
                scenario = await scenario_function()
                scenarios.append(scenario)
            except Exception as exc:
                errors.append(f'{type(exc).__name__}: {exc}')
            await monitor.raise_if_failed()
        key_summary = await _key_summary(redis_client)
        await monitor.stop()
        wall_seconds = time.monotonic() - wall_started
        cpu_seconds = time.process_time() - cpu_started
        final_tasks = len(asyncio.all_tasks())
        redis_end = await read_redis_snapshot(redis_client)
        resource_metrics = monitor.report(wall_seconds=wall_seconds, cpu_seconds=cpu_seconds, final_tasks=final_tasks)
        redis_metrics = redis_delta(redis_start, redis_end, sampled_peak=monitor.redis_peak)
        health_drop_rate = _health_drop_rate(scenarios)
        threshold_checks = _threshold_checks(
            limits,
            resource_metrics,
            redis_metrics,
            health_drop_rate=health_drop_rate,
        )
        dispatcher_sources = min(shape.dispatcher_operations, min(shape.endpoint_count, 1024))
        mixed_sources = min(shape.endpoint_count, 1024)
        expected_zset_members = 2 * (dispatcher_sources + shape.endpoint_count + mixed_sources)
        mixed_health_buckets = math.ceil(shape.mixed_seconds / 10) + 1
        runtime_key_max = mixed_sources * (mixed_health_buckets + 1) + min(shape.endpoint_count, 128) * 3 + 256
        sorted_set_members = key_summary['sorted_set_members']
        runtime_keys = key_summary['keys']
        functional_checks = {
            'no_asyncio_task_leak': final_tasks <= baseline_tasks,
            'all_scenario_checks_passed': all(all(scenario.checks.values()) for scenario in scenarios),
            'tip_member_cardinality_exact': sorted_set_members == expected_zset_members,
            'runtime_key_cardinality_bounded': isinstance(runtime_keys, int) and 0 < runtime_keys <= runtime_key_max,
        }
        functional_pass = not errors and all(functional_checks.values())
        capacity_pass = all(threshold_checks.values())
        report.update(
            {
                'wall_seconds': round(wall_seconds, 6),
                'scenarios': [scenario.json_value() for scenario in scenarios],
                'resources': resource_metrics,
                'redis': redis_metrics,
                'redis_data': key_summary,
                'cardinality_expectations': {
                    'tip_sorted_set_members': expected_zset_members,
                    'runtime_keys_max': runtime_key_max,
                },
                'functional_checks': functional_checks,
                'capacity_checks': threshold_checks,
                'capacity_evidence': {'health_drop_rate': round(health_drop_rate, 6) if health_drop_rate is not None else None},
                'functional_pass': functional_pass,
                'capacity_pass': capacity_pass,
                'errors': errors,
                'notes': [
                    'Latency percentiles use a bounded 20,000-item reservoir.',
                    'Redis command totals include bounded INFO sampling performed by this runner.',
                    'Server lifetime peak memory is informational; sampled peak isolates this run more closely.',
                    'Capacity limits are regression guardrails for the isolated test profile, not production SLOs.',
                    'The page-boundary scenario delays an injected reader; it is not a Redis socket-stall simulation.',
                ],
            }
        )
        success = functional_pass and capacity_pass
    finally:
        if guard_token is not None:
            cleanup = await _cleanup_database(redis_client, guard_token=guard_token)
        await redis_client.aclose()
        report['cleanup'] = cleanup
        if cleanup and (not cleanup['guard_owned'] or cleanup['remaining_keys'] != 0):
            success = False
    return report, success


def _cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def run_stress(args: argparse.Namespace) -> None:
    started_cpu = _cpu_seconds()
    try:
        report, success = asyncio.run(_run(args))
    except Exception as exc:
        report = {
            'success': False,
            'error': f'{type(exc).__name__}: {exc}',
            'process_cpu_seconds': round(_cpu_seconds() - started_cpu, 6),
        }
        success = False
    report['success'] = success
    print(json.dumps(report, indent=2, sort_keys=True))
    if not success:
        sys.exit(1)
