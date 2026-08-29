import argparse
import asyncio
import json
import os
import resource
import sys
import time
from dataclasses import dataclass
from typing import Final

from app.core.config import CONF
from fastlog import configure
from scripts.system_cache_stress.core import run_core
from scripts.system_cache_stress.integration import (
    database_url,
    redis_database_url,
    run_integration,
)
from scripts.system_cache_stress.report import ScenarioReport


@dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    core_concurrency: int
    large_payload_concurrency: int
    integration_concurrency: int
    postgres_rows: int
    payload_bytes: int
    max_rss_growth_mib: int
    max_cpu_percent: int
    max_task_growth: int


PROFILES: Final[dict[str, Profile]] = {
    'quick': Profile(
        core_concurrency=64,
        large_payload_concurrency=64,
        integration_concurrency=16,
        postgres_rows=128,
        payload_bytes=256 * 1024,
        max_rss_growth_mib=256,
        max_cpu_percent=200,
        max_task_growth=2200,
    ),
    'full': Profile(
        core_concurrency=512,
        large_payload_concurrency=128,
        integration_concurrency=32,
        postgres_rows=160,
        payload_bytes=5 * 1024 * 1024,
        max_rss_growth_mib=384,
        max_cpu_percent=200,
        max_task_growth=2200,
    ),
}


def _rss_bytes() -> int:
    try:
        with open('/proc/self/statm') as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, IndexError):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return int(usage.ru_maxrss) * 1024


class ResourceMonitor:
    def __init__(self) -> None:
        self.peak_rss_bytes = _rss_bytes()
        self.peak_tasks = len(asyncio.all_tasks())
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._sample())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _sample(self) -> None:
        while not self._stop.is_set():
            self.peak_rss_bytes = max(self.peak_rss_bytes, _rss_bytes())
            self.peak_tasks = max(self.peak_tasks, len(asyncio.all_tasks()))
            try:
                async with asyncio.timeout(0.05):
                    await self._stop.wait()
            except TimeoutError:
                pass


async def _run(args: argparse.Namespace) -> tuple[dict[str, object], bool]:
    profile = PROFILES[args.profile]
    core_concurrency = args.concurrency or profile.core_concurrency
    if core_concurrency > 4096:
        raise ValueError('Stress concurrency cannot exceed 4096.')
    integration_concurrency = min(core_concurrency, profile.integration_concurrency)
    redis_url = args.redis_url or os.getenv('SYSTEM_CACHE_STRESS_REDIS_URL')
    postgres_url = args.postgres_url or os.getenv('SYSTEM_CACHE_STRESS_POSTGRES_URL')
    if args.redis_db is not None:
        if redis_url is not None:
            raise ValueError('Use either --redis-url or --redis-db, not both.')
        redis_url = redis_database_url(CONF.REDIS_URL, args.redis_db)
    if args.postgres_database is not None:
        if postgres_url is not None:
            raise ValueError('Use either --postgres-url or --postgres-database, not both.')
        postgres_url = database_url(CONF.ORM_URL, args.postgres_database)
    if args.mode in {'integration', 'all'} and (not redis_url or not postgres_url):
        raise ValueError('Integration mode requires dedicated Redis and PostgreSQL stress URLs.')

    baseline_rss = _rss_bytes()
    baseline_tasks = len(asyncio.all_tasks())
    wall_started = time.monotonic()
    cpu_started = time.process_time()
    monitor = ResourceMonitor()
    monitor.start()
    scenarios: list[ScenarioReport] = []
    integration_target: dict[str, object] | None = None
    try:
        if args.mode in {'core', 'all'}:
            scenarios.extend(
                await run_core(
                    CONF.SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN,
                    concurrency=core_concurrency,
                    large_payload_concurrency=min(core_concurrency, profile.large_payload_concurrency),
                    payload_bytes=profile.payload_bytes,
                )
            )
        if args.mode in {'integration', 'all'}:
            if redis_url is None or postgres_url is None:
                raise RuntimeError('Integration URLs disappeared after validation.')
            integration_reports, integration_target = await run_integration(
                redis_url,
                postgres_url,
                CONF.SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN,
                concurrency=integration_concurrency,
                rows=profile.postgres_rows,
                payload_bytes=profile.payload_bytes,
            )
            scenarios.extend(integration_reports)
    finally:
        await monitor.stop()
    wall_seconds = time.monotonic() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    final_tasks = len(asyncio.all_tasks())
    rss_growth = max(0, monitor.peak_rss_bytes - baseline_rss)
    cpu_percent = cpu_seconds / wall_seconds * 100 if wall_seconds else 0.0
    functional_checks = {
        'all_scenarios_passed': all(all(scenario.checks.values()) for scenario in scenarios),
        'no_task_leak': final_tasks <= baseline_tasks,
    }
    capacity_checks = {
        'rss_growth_bounded': rss_growth <= profile.max_rss_growth_mib * 1024 * 1024,
        'parent_cpu_bounded': cpu_percent <= profile.max_cpu_percent,
        'task_growth_bounded': monitor.peak_tasks - baseline_tasks <= max(profile.max_task_growth, core_concurrency + 4),
    }
    success = bool(scenarios) and all(functional_checks.values()) and all(capacity_checks.values())
    report: dict[str, object] = {
        'mode': args.mode,
        'evidence_level': 'integrated' if args.mode in {'integration', 'all'} else 'synthetic',
        'profile': args.profile,
        'shape': {
            'core_concurrency': core_concurrency,
            'large_payload_concurrency': min(core_concurrency, profile.large_payload_concurrency),
            'integration_concurrency': integration_concurrency,
            'postgres_rows': profile.postgres_rows,
            'payload_bytes': profile.payload_bytes,
        },
        'retention_seconds': {
            chain.value: seconds for chain, seconds in CONF.SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN.items()
        },
        'scenarios': [scenario.json_value() for scenario in scenarios],
        'resources': {
            'wall_seconds': round(wall_seconds, 6),
            'parent_cpu_seconds': round(cpu_seconds, 6),
            'parent_cpu_percent_one_core': round(cpu_percent, 3),
            'rss_baseline_bytes': baseline_rss,
            'rss_peak_bytes': monitor.peak_rss_bytes,
            'rss_growth_bytes': rss_growth,
            'asyncio_tasks_baseline': baseline_tasks,
            'asyncio_tasks_peak': monitor.peak_tasks,
            'asyncio_tasks_final': final_tasks,
        },
        'resource_measurement_scope': {
            'parent_process': True,
            'worker_processes': args.mode in {'integration', 'all'},
            'redis_server_cpu': args.mode in {'integration', 'all'},
            'postgres_server_cpu': False,
        },
        'functional_checks': functional_checks,
        'capacity_checks': capacity_checks,
        'integration_target': integration_target,
        'success': success,
    }
    return report, success


def run_stress(args: argparse.Namespace) -> None:
    configure(level='error')
    try:
        report, success = asyncio.run(_run(args))
    except Exception as exc:
        report = {'success': False, 'error': f'{type(exc).__name__}: {exc}'}
        success = False
    print(json.dumps(report, indent=2, sort_keys=True))
    if not success:
        sys.exit(1)
