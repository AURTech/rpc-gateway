import asyncio
import math
import os
import random
import resource
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from redis.asyncio import Redis

MAX_LATENCY_SAMPLES: Final[int] = 20_000
MAX_RESOURCE_SAMPLES: Final[int] = 4096
COMMANDS: Final[tuple[str, ...]] = (
    'eval',
    'evalsha',
    'time',
    'hmget',
    'hgetall',
    'hset',
    'hlen',
    'zadd',
    'zcard',
    'zrangebylex',
    'zrangebyscore',
    'zrem',
    'expire',
    'pexpire',
    'pexpireat',
    'set',
    'get',
    'del',
    'unlink',
)


def _number(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str | bytes):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    position = math.ceil(percentile * len(values)) - 1
    return values[max(0, position)]


def read_rss_bytes() -> int:
    statm = Path('/proc/self/statm')
    if statm.exists():
        fields = statm.read_text(encoding='ascii').split()
        if len(fields) >= 2:
            return int(fields[1]) * os.sysconf('SC_PAGE_SIZE')
    peak_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak_kib * 1024)


@dataclass(slots=True)
class LatencyStats:
    count: int = 0
    total_ms: float = 0.0
    maximum_ms: float = 0.0
    _samples: list[float] = field(default_factory=list)
    _random: random.Random = field(default_factory=lambda: random.Random(0xA17E))

    def add(self, elapsed_seconds: float) -> None:
        milliseconds = elapsed_seconds * 1000
        self.count += 1
        self.total_ms += milliseconds
        self.maximum_ms = max(self.maximum_ms, milliseconds)
        if len(self._samples) < MAX_LATENCY_SAMPLES:
            self._samples.append(milliseconds)
            return
        position = self._random.randrange(self.count)
        if position < MAX_LATENCY_SAMPLES:
            self._samples[position] = milliseconds

    def report(self) -> dict[str, float | int]:
        values = sorted(self._samples)
        mean = self.total_ms / self.count if self.count else 0.0
        return {
            'count': self.count,
            'sample_count': len(values),
            'mean_ms': round(mean, 3),
            'p50_ms': round(_percentile(values, 0.50), 3),
            'p95_ms': round(_percentile(values, 0.95), 3),
            'p99_ms': round(_percentile(values, 0.99), 3),
            'max_ms': round(self.maximum_ms, 3),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RedisSnapshot:
    used_memory: int
    used_memory_peak: int
    cpu_user: float
    cpu_sys: float
    commands: int
    command_calls: dict[str, int]
    command_usec: dict[str, int]


async def read_redis_snapshot(redis_client: Redis) -> RedisSnapshot:
    async with redis_client.pipeline(transaction=False) as pipeline:
        pipeline.info('memory')
        pipeline.info('cpu')
        pipeline.info('stats')
        pipeline.info('commandstats')
        memory_raw, cpu_raw, stats_raw, command_raw = await pipeline.execute()
    memory = _mapping(memory_raw)
    cpu = _mapping(cpu_raw)
    stats = _mapping(stats_raw)
    commandstats = _mapping(command_raw)
    calls: dict[str, int] = {}
    usec: dict[str, int] = {}
    for command in COMMANDS:
        details = _mapping(commandstats.get(f'cmdstat_{command}'))
        calls[command] = int(_number(details.get('calls')))
        usec[command] = int(_number(details.get('usec')))
    return RedisSnapshot(
        used_memory=int(_number(memory.get('used_memory'))),
        used_memory_peak=int(_number(memory.get('used_memory_peak'))),
        cpu_user=_number(cpu.get('used_cpu_user')),
        cpu_sys=_number(cpu.get('used_cpu_sys')),
        commands=int(_number(stats.get('total_commands_processed'))),
        command_calls=calls,
        command_usec=usec,
    )


def redis_delta(start: RedisSnapshot, end: RedisSnapshot, *, sampled_peak: int) -> dict[str, object]:
    commandstats: dict[str, dict[str, int]] = {}
    for command in COMMANDS:
        calls = end.command_calls[command] - start.command_calls[command]
        usec = end.command_usec[command] - start.command_usec[command]
        if calls or usec:
            commandstats[command] = {'calls': calls, 'usec': usec}
    return {
        'used_memory_start_bytes': start.used_memory,
        'used_memory_end_bytes': end.used_memory,
        'used_memory_sampled_peak_bytes': sampled_peak,
        'server_lifetime_peak_bytes': end.used_memory_peak,
        'cpu_user_seconds': round(end.cpu_user - start.cpu_user, 6),
        'cpu_sys_seconds': round(end.cpu_sys - start.cpu_sys, 6),
        'commands': end.commands - start.commands,
        'commandstats': commandstats,
    }


@dataclass(slots=True, kw_only=True)
class ResourceMonitor:
    redis_client: Redis
    sample_interval: float
    baseline_tasks: int
    start_rss: int = field(default_factory=read_rss_bytes)
    peak_rss: int = 0
    peak_tasks: int = 0
    redis_peak: int = 0
    process_cpu_peak_percent: float = 0.0
    redis_cpu_peak_percent: float = 0.0
    samples: int = 0
    _task: asyncio.Task[None] | None = None
    _last_wall: float = 0.0
    _last_process_cpu: float = 0.0
    _last_redis_wall: float = 0.0
    _last_redis_cpu: float | None = None
    _rss_samples: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=MAX_RESOURCE_SAMPLES))

    def start(self) -> None:
        self.peak_rss = self.start_rss
        self.peak_tasks = self.baseline_tasks
        self._last_wall = time.monotonic()
        self._last_process_cpu = time.process_time()
        self._task = asyncio.create_task(self._sample(), name='runtime-state-stress-monitor')

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            raise RuntimeError('Runtime State resource monitor failed.') from exc
        finally:
            self._task = None
            self._sample_local()

    async def raise_if_failed(self) -> None:
        task = self._task
        if task is None or not task.done():
            return
        try:
            await task
        except asyncio.CancelledError:
            raise RuntimeError('Runtime State resource monitor stopped unexpectedly.') from None
        except Exception as exc:
            raise RuntimeError('Runtime State resource monitor failed.') from exc
        raise RuntimeError('Runtime State resource monitor stopped unexpectedly.')

    def report(self, *, wall_seconds: float, cpu_seconds: float, final_tasks: int) -> dict[str, float | int]:
        cpu_percent = cpu_seconds / wall_seconds * 100 if wall_seconds > 0 else 0.0
        return {
            'rss_start_bytes': self.start_rss,
            'rss_end_bytes': read_rss_bytes(),
            'rss_peak_bytes': self.peak_rss,
            'rss_growth_bytes': max(0, self.peak_rss - self.start_rss),
            'rss_slope_bytes_per_minute': round(self._rss_slope(), 3),
            'process_cpu_seconds': round(cpu_seconds, 6),
            'process_cpu_percent_one_core': round(cpu_percent, 3),
            'process_cpu_peak_percent_one_core': round(self.process_cpu_peak_percent, 3),
            'redis_cpu_peak_percent_one_core': round(self.redis_cpu_peak_percent, 3),
            'asyncio_tasks_baseline': self.baseline_tasks,
            'asyncio_tasks_peak': self.peak_tasks,
            'asyncio_tasks_final': final_tasks,
            'samples': self.samples,
        }

    async def _sample(self) -> None:
        while True:
            self._sample_local()
            try:
                async with self.redis_client.pipeline(transaction=False) as pipeline:
                    pipeline.info('memory')
                    pipeline.info('cpu')
                    memory, cpu = await pipeline.execute()
                self.redis_peak = max(self.redis_peak, int(_number(_mapping(memory).get('used_memory'))))
                self._sample_redis_cpu(_mapping(cpu))
            finally:
                self.samples += 1
            await asyncio.sleep(self.sample_interval)

    def _sample_local(self) -> None:
        now = time.monotonic()
        process_cpu = time.process_time()
        elapsed = now - self._last_wall
        if elapsed > 0:
            cpu_percent = (process_cpu - self._last_process_cpu) / elapsed * 100
            self.process_cpu_peak_percent = max(self.process_cpu_peak_percent, cpu_percent)
        self._last_wall = now
        self._last_process_cpu = process_cpu
        rss = read_rss_bytes()
        self.peak_rss = max(self.peak_rss, rss)
        self.peak_tasks = max(self.peak_tasks, len(asyncio.all_tasks()))
        self._rss_samples.append((now, rss))

    def _rss_slope(self) -> float:
        if len(self._rss_samples) < 2:
            return 0.0
        origin = self._rss_samples[0][0]
        xs = [sample_time - origin for sample_time, _ in self._rss_samples]
        ys = [float(rss) for _, rss in self._rss_samples]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        variance = sum((value - mean_x) ** 2 for value in xs)
        if variance == 0:
            return 0.0
        covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        return covariance / variance * 60

    def _sample_redis_cpu(self, cpu: dict[str, object]) -> None:
        now = time.monotonic()
        total = _number(cpu.get('used_cpu_user')) + _number(cpu.get('used_cpu_sys'))
        if self._last_redis_cpu is not None:
            elapsed = now - self._last_redis_wall
            if elapsed > 0:
                cpu_percent = (total - self._last_redis_cpu) / elapsed * 100
                self.redis_cpu_peak_percent = max(self.redis_cpu_peak_percent, cpu_percent)
        self._last_redis_wall = now
        self._last_redis_cpu = total


@dataclass(frozen=True, slots=True, kw_only=True)
class ScenarioReport:
    name: str
    wall_seconds: float
    operations: int
    throughput_per_second: float
    latency: dict[str, float | int]
    counts: dict[str, int]
    checks: dict[str, bool]
    details: dict[str, object]

    def json_value(self) -> dict[str, object]:
        return asdict(self)


def scenario_report(
    *,
    name: str,
    started_at: float,
    operations: int,
    latency: LatencyStats,
    counts: dict[str, int],
    checks: dict[str, bool],
    details: dict[str, object] | None = None,
) -> ScenarioReport:
    wall_seconds = time.monotonic() - started_at
    throughput = operations / wall_seconds if wall_seconds > 0 else 0.0
    return ScenarioReport(
        name=name,
        wall_seconds=round(wall_seconds, 6),
        operations=operations,
        throughput_per_second=round(throughput, 3),
        latency=latency.report(),
        counts=counts,
        checks=checks,
        details=details or {},
    )
