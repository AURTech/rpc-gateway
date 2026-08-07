import secrets
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from redis.asyncio import Redis

from app.infra import redis
from app.model.blockchain import Chain, Network
from app.model.runtime_state.chain.tip import ChainTip
from app.model.runtime_state.tip import Finality, TipUnit
from app.util.datetime import to_epoch_micros

LEASE_TIMEOUT_FACTOR: Final[int] = 4

_ACQUIRE_LUA: Final[str] = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return {0}
end
local fence = redis.call('INCR', KEYS[2])
redis.call('PSETEX', KEYS[1], ARGV[1], ARGV[2] .. ':' .. fence)
local redis_time = redis.call('TIME')
return {fence, redis_time[1], redis_time[2]}
"""

_RENEW_LUA: Final[str] = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return {0}
end
redis.call('PEXPIRE', KEYS[1], ARGV[2])
local redis_time = redis.call('TIME')
return {1, redis_time[1], redis_time[2]}
"""

_COMMIT_LUA: Final[str] = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return {0}
end
local fence = tonumber(ARGV[2])
local saved = tonumber(redis.call('HGET', KEYS[2], 'fence') or '0')
if not fence or saved >= fence then
    return {0}
end
local redis_time = redis.call('TIME')
local redis_now_micros = tonumber(redis_time[1]) * 1000000 + tonumber(redis_time[2])
local ttl_ms = math.floor((tonumber(ARGV[7]) - redis_now_micros) / 1000)
if ttl_ms < 1 then
    return {0, redis_time[1], redis_time[2]}
end
redis.call(
    'HSET', KEYS[2],
    'fence', ARGV[2],
    'value', ARGV[3],
    'source_count', ARGV[4],
    'observed_at', ARGV[5],
    'computed_at', ARGV[6],
    'valid_until', ARGV[7]
)
redis.call('PEXPIRE', KEYS[2], ttl_ms)
return {1, redis_time[1], redis_time[2]}
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class RedisClock:
    now: datetime
    anchor: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ChainTipRead:
    tip: ChainTip | None
    clock: RedisClock


@dataclass(frozen=True, slots=True, kw_only=True)
class ChainTipWrite:
    applied: bool
    clock: RedisClock | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ChainTipLease:
    lock_key: str
    snapshot_key: str
    owner: str
    fence: int
    clock: RedisClock
    renew_after_seconds: float


def _dimension_tag(*, chain: Chain, network: Network, unit: TipUnit, finality: Finality) -> str:
    return f'{{{chain.value}|{network.value}|{unit.value}|{finality.value}}}'


def _snapshot_key(*, chain: Chain, network: Network, unit: TipUnit, finality: Finality) -> str:
    tag = _dimension_tag(chain=chain, network=network, unit=unit, finality=finality)
    return redis.build_key(
        'runtime_state',
        'v2',
        'chain',
        'tip',
        tag,
        'snapshot',
    )


def _lock_key(*, chain: Chain, network: Network, unit: TipUnit, finality: Finality) -> str:
    tag = _dimension_tag(chain=chain, network=network, unit=unit, finality=finality)
    return redis.build_key(
        'runtime_state',
        'v2',
        'chain',
        'tip',
        tag,
        'lock',
    )


def _fence_key(*, chain: Chain, network: Network, unit: TipUnit, finality: Finality) -> str:
    tag = _dimension_tag(chain=chain, network=network, unit=unit, finality=finality)
    return redis.build_key(
        'runtime_state',
        'v2',
        'chain',
        'tip',
        tag,
        'fence',
    )


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


def _from_micros(value: object) -> datetime | None:
    micros = _to_int(value)
    if micros is None:
        return None
    try:
        return datetime.fromtimestamp(micros / 1_000_000, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _redis_time(raw: object, *, anchor: float) -> RedisClock:
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        raise RuntimeError('Redis returned an invalid chain tip time.')
    seconds = _to_int(raw[0])
    micros = _to_int(raw[1])
    if seconds is None or seconds < 0 or micros is None or not 0 <= micros < 1_000_000:
        raise RuntimeError('Redis returned an invalid chain tip time.')
    try:
        now = datetime.fromtimestamp(seconds, tz=UTC) + timedelta(microseconds=micros)
    except (OSError, OverflowError, ValueError) as exc:
        raise RuntimeError('Redis returned an invalid chain tip time.') from exc
    return RedisClock(now=now, anchor=anchor)


def _script_clock(raw: object, *, expected: int, anchor: float) -> RedisClock | None:
    if not isinstance(raw, list | tuple) or not raw:
        raise RuntimeError('Chain tip lease result is invalid.')
    result = _to_int(raw[0])
    if result == 0 and len(raw) == 1:
        return None
    if result != expected or len(raw) != 3:
        raise RuntimeError('Chain tip lease result is invalid.')
    return _redis_time((raw[1], raw[2]), anchor=anchor)


def _parse_snapshot(
    raw: object,
    *,
    chain: Chain,
    network: Network,
    unit: TipUnit,
    finality: Finality,
) -> ChainTip | None:
    if not isinstance(raw, Mapping) or not raw:
        return None
    fields: dict[str, object] = {_to_text(key): value for key, value in raw.items()}
    value = _to_int(fields.get('value'))
    source_count = _to_int(fields.get('source_count'))
    observed_at = _from_micros(fields.get('observed_at'))
    computed_at = _from_micros(fields.get('computed_at'))
    valid_until = _from_micros(fields.get('valid_until'))
    if value is None or source_count is None or observed_at is None or computed_at is None or valid_until is None:
        return None
    try:
        return ChainTip(
            chain=chain,
            network=network,
            unit=unit,
            finality=finality,
            value=value,
            source_count=source_count,
            observed_at=observed_at,
            computed_at=computed_at,
            valid_until=valid_until,
        )
    except ValueError:
        return None


class ChainTipStore:
    def __init__(
        self,
        redis_client: Redis,
        *,
        max_redis_io_ms: int,
        lock_ttl_ms: int | None = None,
    ) -> None:
        """Build a store whose lease survives a page read followed by a renewal.

        `max_redis_io_ms` must be at least the Redis client's socket timeout. The derived lease
        reserves one I/O window before renewal, one for a late page, one for renewal, and one as
        margin.
        """
        if isinstance(max_redis_io_ms, bool) or max_redis_io_ms < 1:
            raise ValueError('Maximum Redis I/O time must be positive.')
        required_ttl_ms = max_redis_io_ms * LEASE_TIMEOUT_FACTOR
        if lock_ttl_ms is None:
            lock_ttl_ms = required_ttl_ms
        if isinstance(lock_ttl_ms, bool) or lock_ttl_ms < required_ttl_ms:
            raise ValueError('Chain tip lock TTL does not satisfy its Redis I/O safety margin.')
        self._redis = redis_client
        self._lock_ttl_ms = lock_ttl_ms
        self._acquire = redis_client.register_script(_ACQUIRE_LUA)
        self._renew = redis_client.register_script(_RENEW_LUA)
        self._commit = redis_client.register_script(_COMMIT_LUA)

    async def get(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> ChainTipRead:
        key = _snapshot_key(chain=chain, network=network, unit=unit, finality=finality)
        anchor = time.monotonic()
        async with self._redis.pipeline(transaction=False) as pipeline:
            pipeline.hgetall(key)
            pipeline.time()
            raw, raw_time = await pipeline.execute()
        clock = _redis_time(raw_time, anchor=anchor)
        tip = _parse_snapshot(raw, chain=chain, network=network, unit=unit, finality=finality)
        return ChainTipRead(tip=tip, clock=clock)

    async def put(self, tip: ChainTip, *, lease: ChainTipLease) -> ChainTipWrite:
        """Commit a snapshot only while the caller still owns its fenced dimension lease."""
        key = _snapshot_key(chain=tip.chain, network=tip.network, unit=tip.unit, finality=tip.finality)
        if lease.snapshot_key != key:
            raise ValueError('Chain tip lease dimension does not match the snapshot.')
        anchor = time.monotonic()
        raw = await self._commit(
            keys=[lease.lock_key, key],
            args=[
                lease.owner,
                lease.fence,
                tip.value,
                tip.source_count,
                to_epoch_micros(tip.observed_at),
                to_epoch_micros(tip.computed_at),
                to_epoch_micros(tip.valid_until),
            ],
        )
        if not isinstance(raw, list | tuple) or not raw:
            raise RuntimeError('Chain tip commit result is invalid.')
        applied = _to_int(raw[0])
        if applied == 0 and len(raw) == 1:
            return ChainTipWrite(applied=False, clock=None)
        if applied not in (0, 1) or len(raw) != 3:
            raise RuntimeError('Chain tip commit result is invalid.')
        clock = _redis_time((raw[1], raw[2]), anchor=anchor)
        return ChainTipWrite(applied=applied == 1, clock=clock)

    async def renew(self, lease: ChainTipLease) -> RedisClock | None:
        """Extend a lease only while its complete owner and fence token still match."""
        anchor = time.monotonic()
        raw = await self._renew(
            keys=[lease.lock_key],
            args=[lease.owner, self._lock_ttl_ms],
        )
        return _script_clock(raw, expected=1, anchor=anchor)

    @asynccontextmanager
    async def lock(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> AsyncIterator[ChainTipLease | None]:
        lock_key = _lock_key(chain=chain, network=network, unit=unit, finality=finality)
        fence_key = _fence_key(chain=chain, network=network, unit=unit, finality=finality)
        snapshot_key = _snapshot_key(chain=chain, network=network, unit=unit, finality=finality)
        token = secrets.token_urlsafe(16)
        anchor = time.monotonic()
        raw = await self._acquire(
            keys=[lock_key, fence_key],
            args=[self._lock_ttl_ms, token],
        )
        if not isinstance(raw, list | tuple) or not raw:
            raise RuntimeError('Chain tip lease result is invalid.')
        fence = _to_int(raw[0])
        lease = None
        if fence is not None and fence > 0:
            if len(raw) != 3:
                raise RuntimeError('Chain tip lease result is invalid.')
            lease = ChainTipLease(
                lock_key=lock_key,
                snapshot_key=snapshot_key,
                owner=f'{token}:{fence}',
                fence=fence,
                clock=_redis_time((raw[1], raw[2]), anchor=anchor),
                renew_after_seconds=self._lock_ttl_ms / (LEASE_TIMEOUT_FACTOR * 1000),
            )
        elif fence != 0 or len(raw) != 1:
            raise RuntimeError('Chain tip lease result is invalid.')
        try:
            yield lease
        finally:
            if lease is not None:
                await redis.delete_string_if_value(self._redis, lock_key, lease.owner)
