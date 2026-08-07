from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from fastlog import log
from redis.asyncio import Redis
from redis.exceptions import WatchError

from app.infra import redis
from app.model.runtime_state.endpoint.health import EndpointHealth, HealthStatus
from app.services.runtime_state.endpoint.health.state import (
    HEALTH_BUCKET_SECONDS,
    HEALTH_WINDOW_SECONDS,
    HealthBatch,
    WindowStats,
    bucket_epoch,
    build_health,
    with_window,
)
from app.util.datetime import to_epoch_micros

HEALTH_STALE_SECONDS: Final[int] = 5 * 60
HEALTH_BUCKET_LATE_WRITE_MARGIN_SECONDS: Final[int] = 20
HEALTH_FUTURE_SKEW_SECONDS: Final[int] = 5
HEALTH_SNAPSHOT_TTL_SECONDS: Final[int] = 24 * 60 * 60
HEALTH_WATCH_RETRIES: Final[int] = 3
_HEALTH_WINDOW_BUCKETS: Final[int] = HEALTH_WINDOW_SECONDS // HEALTH_BUCKET_SECONDS
_HEALTH_OLDEST_BUCKET_OFFSET_SECONDS: Final[int] = HEALTH_WINDOW_SECONDS - HEALTH_BUCKET_SECONDS
_HEALTH_BUCKET_RETENTION_SECONDS: Final[int] = HEALTH_WINDOW_SECONDS + HEALTH_BUCKET_LATE_WRITE_MARGIN_SECONDS
_HEALTH_BUCKET_RING_SLOTS: Final[int] = _HEALTH_WINDOW_BUCKETS + 1

_INCREMENT_BUCKET_LUA = """
local bucket_epoch = tonumber(ARGV[1])
local observed_micros = tonumber(ARGV[2])
local parts = redis.call('TIME')
local redis_epoch = tonumber(parts[1])
local redis_micros = redis_epoch * 1000000 + tonumber(parts[2])
local anchor_epoch = redis_epoch - (redis_epoch % tonumber(ARGV[3]))

if bucket_epoch < anchor_epoch - tonumber(ARGV[4]) then
    return {2, parts[1], parts[2]}
end
if observed_micros > redis_micros + tonumber(ARGV[5]) or bucket_epoch > anchor_epoch + tonumber(ARGV[3]) then
    return {3, parts[1], parts[2]}
end

local slot = tostring(bucket_epoch % tonumber(ARGV[10]))
local raw = redis.call('HGET', KEYS[1], slot)
local samples = 0
local successes = 0
local failures = 0
local latency_micros = 0
if raw then
    local saved_epoch, saved_samples, saved_successes, saved_failures, saved_latency =
        string.match(raw, '^(%-?%d+):(%d+):(%d+):(%d+):(%d+)$')
    if not saved_epoch then
        return {4, parts[1], parts[2]}
    end
    if tonumber(saved_epoch) == bucket_epoch then
        samples = tonumber(saved_samples)
        successes = tonumber(saved_successes)
        failures = tonumber(saved_failures)
        latency_micros = tonumber(saved_latency)
    end
end
local packed = string.format(
    '%.0f:%.0f:%.0f:%.0f:%.0f',
    bucket_epoch,
    samples + tonumber(ARGV[6]),
    successes + tonumber(ARGV[7]),
    failures + tonumber(ARGV[8]),
    latency_micros + tonumber(ARGV[9])
)
redis.call('HSET', KEYS[1], slot, packed)
redis.call('EXPIRE', KEYS[1], ARGV[11])
return {1, parts[1], parts[2]}
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class _StoredHealth:
    health: EndpointHealth
    version: int
    observed_at: datetime


def _to_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, str):
        return value
    return str(value)


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str | bytes):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _bucket_key(*, endpoint_id: str, endpoint_version: int) -> str:
    return redis.build_key(
        'runtime_state',
        'v2',
        'health',
        'bucket',
        endpoint_id,
        str(endpoint_version),
    )


def _snapshot_key(endpoint_id: str) -> str:
    return redis.build_key('runtime_state', 'v2', 'health', 'snapshot', endpoint_id)


def _parse_snapshot(raw: object) -> _StoredHealth | None:
    if not isinstance(raw, Mapping) or not raw:
        return None
    fields = {_to_text(key): value for key, value in raw.items()}
    payload = fields.get('payload')
    version = _to_int(fields.get('version'))
    observed_micros = _to_int(fields.get('observed_at'))
    if payload is None or version is None or version < 1 or observed_micros is None:
        return None
    try:
        health = EndpointHealth.model_validate_json(_to_text(payload))
        observed_at = datetime.fromtimestamp(observed_micros / 1_000_000, tz=UTC)
    except (ValueError, OverflowError):
        return None
    if health.last_observed_at != observed_at:
        return None
    return _StoredHealth(health=health, version=version, observed_at=observed_at)


def _parse_bucket(raw: object, *, epochs: set[int]) -> WindowStats:
    if not isinstance(raw, Mapping) or not raw:
        return WindowStats(samples=0, successes=0, failures=0, success_latency_micros=0)
    samples = 0
    successes = 0
    failures = 0
    latency_micros = 0
    for value in raw.values():
        fields = _to_text(value).split(':')
        if len(fields) != 5:
            raise RuntimeError('Health bucket data is invalid.')
        epoch = _to_int(fields[0])
        added_samples = _to_int(fields[1])
        added_successes = _to_int(fields[2])
        added_failures = _to_int(fields[3])
        added_latency = _to_int(fields[4])
        if epoch is None or added_samples is None or added_successes is None or added_failures is None or added_latency is None:
            raise RuntimeError('Health bucket data is invalid.')
        if min(epoch, added_samples, added_successes, added_failures, added_latency) < 0:
            raise RuntimeError('Health bucket data is invalid.')
        if added_samples != added_successes + added_failures:
            raise RuntimeError('Health bucket counters are inconsistent.')
        if epoch not in epochs:
            continue
        samples += added_samples
        successes += added_successes
        failures += added_failures
        latency_micros += added_latency
    return WindowStats(
        samples=samples,
        successes=successes,
        failures=failures,
        success_latency_micros=latency_micros,
    )


class HealthStore:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._increment = redis_client.register_script(_INCREMENT_BUCKET_LUA)

    async def record(self, batch: HealthBatch) -> EndpointHealth:
        """Record an aggregate exactly once; callers must not retry ambiguous writes."""
        anchor_epoch = await self._increment_bucket(batch)
        return await self._save_snapshot(batch, anchor_epoch=anchor_epoch)

    async def get(self, endpoint_id: str, endpoint_version: int) -> EndpointHealth | None:
        key = _snapshot_key(endpoint_id)
        async with self._redis.pipeline(transaction=False) as pipeline:
            pipeline.time()
            pipeline.hgetall(key)
            result = await pipeline.execute()
        if not isinstance(result, list | tuple) or len(result) != 2:
            raise RuntimeError('Redis returned an invalid health read result.')
        now = _parse_redis_time(result[0])
        raw = result[1]
        stored = _parse_snapshot(raw)
        if stored is None:
            if raw and await self._delete_invalid_snapshot(key=key, expected=raw):
                log.warning(f'Endpoint health snapshot removed after invalid Redis data | Key:{key}')
            return None
        if stored.version != endpoint_version:
            return None
        if now - stored.observed_at >= timedelta(seconds=HEALTH_STALE_SECONDS):
            return stored.health.model_copy(
                update={
                    'status': HealthStatus.UNKNOWN,
                    'error_rate': 0.0,
                    'latency_ms': None,
                    'samples': 0,
                }
            )
        stats = await self._read_window(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            anchor_epoch=bucket_epoch(now),
        )
        return with_window(stored.health, stats)

    async def _increment_bucket(self, batch: HealthBatch) -> int:
        if bucket_epoch(batch.last_observed_at) != batch.bucket_epoch:
            raise RuntimeError('Health batch time does not match its bucket.')
        key = _bucket_key(
            endpoint_id=batch.endpoint_id,
            endpoint_version=batch.endpoint_version,
        )
        raw = await self._increment(
            keys=[key],
            args=[
                batch.bucket_epoch,
                to_epoch_micros(batch.last_observed_at),
                HEALTH_BUCKET_SECONDS,
                _HEALTH_OLDEST_BUCKET_OFFSET_SECONDS,
                HEALTH_FUTURE_SKEW_SECONDS * 1_000_000,
                batch.samples,
                batch.successes,
                batch.failures,
                batch.success_latency_micros,
                _HEALTH_BUCKET_RING_SLOTS,
                _HEALTH_BUCKET_RETENTION_SECONDS,
            ],
        )
        status, now = _parse_bucket_write(raw)
        if status == 2:
            raise RuntimeError('Health observation is outside the live window.')
        if status == 3:
            raise RuntimeError('Health observation time is too far in the future.')
        if status == 4:
            raise RuntimeError('Health bucket data is invalid.')
        return bucket_epoch(now)

    async def _read_window(
        self,
        *,
        endpoint_id: str,
        endpoint_version: int,
        anchor_epoch: int,
    ) -> WindowStats:
        key = _bucket_key(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
        )
        epochs = {anchor_epoch - offset * HEALTH_BUCKET_SECONDS for offset in range(_HEALTH_WINDOW_BUCKETS)}
        # Reason: redis.asyncio commands are awaitable at runtime; stubs include a sync branch.
        raw = await self._redis.hgetall(key)  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
        return _parse_bucket(
            raw,
            epochs=epochs,
        )

    async def _save_snapshot(self, batch: HealthBatch, *, anchor_epoch: int) -> EndpointHealth:
        key = _snapshot_key(batch.endpoint_id)
        for _ in range(HEALTH_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)
                    # Reason: redis.asyncio pipeline commands are awaitable before MULTI; stubs include a sync branch.
                    raw = await pipeline.hgetall(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
                        key
                    )
                    stored = _parse_snapshot(raw)
                    if stored is not None and (
                        batch.endpoint_version < stored.version
                        or (batch.endpoint_version == stored.version and batch.last_observed_at <= stored.observed_at)
                    ):
                        stats = await self._read_window(
                            endpoint_id=batch.endpoint_id,
                            endpoint_version=stored.version,
                            anchor_epoch=anchor_epoch,
                        )
                        return with_window(stored.health, stats)
                    stats = await self._read_window(
                        endpoint_id=batch.endpoint_id,
                        endpoint_version=batch.endpoint_version,
                        anchor_epoch=anchor_epoch,
                    )
                    saved_health = stored.health if stored is not None and stored.version == batch.endpoint_version else None
                    health = build_health(batch, stats, saved_health)
                    pipeline.multi()
                    pipeline.hset(
                        key,
                        mapping={
                            'payload': health.model_dump_json(),
                            'version': batch.endpoint_version,
                            'observed_at': to_epoch_micros(batch.last_observed_at),
                        },
                    )
                    pipeline.expire(key, HEALTH_SNAPSHOT_TTL_SECONDS)
                    await pipeline.execute()
                    return health
                except WatchError:
                    continue
        raise RuntimeError('Endpoint health write exceeded its concurrency retry limit.')

    async def _delete_invalid_snapshot(self, *, key: str, expected: object) -> bool:
        for _ in range(HEALTH_WATCH_RETRIES):
            async with self._redis.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)
                    # Reason: redis.asyncio pipeline commands are awaitable before MULTI; stubs include a sync branch.
                    saved = await pipeline.hgetall(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
                        key
                    )
                    if saved != expected:
                        return False
                    pipeline.multi()
                    pipeline.delete(key)
                    await pipeline.execute()
                    return True
                except WatchError:
                    continue
        return False


def _parse_redis_time(raw: object) -> datetime:
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        raise RuntimeError('Redis returned an invalid health time.')
    seconds = _to_int(raw[0])
    micros = _to_int(raw[1])
    if seconds is None or seconds < 0 or micros is None or not 0 <= micros < 1_000_000:
        raise RuntimeError('Redis returned an invalid health time.')
    try:
        return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(microseconds=micros)
    except (ValueError, OverflowError, OSError) as exc:
        raise RuntimeError('Redis returned an invalid health time.') from exc


def _parse_bucket_write(raw: object) -> tuple[int, datetime]:
    if not isinstance(raw, list | tuple) or len(raw) != 3:
        raise RuntimeError('Redis returned an invalid health bucket result.')
    status = _to_int(raw[0])
    if status not in (1, 2, 3, 4):
        raise RuntimeError('Redis returned an invalid health bucket result.')
    return status, _parse_redis_time(raw[1:])
