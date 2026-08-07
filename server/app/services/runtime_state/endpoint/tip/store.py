from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from redis.asyncio import Redis

from app.services.runtime_state.endpoint.tip.write import TipWriteResult
from app.util.datetime import to_epoch_micros

READ_PAGE_SIZE: Final[int] = 256
PUT_CLEANUP_LIMIT: Final[int] = 16
MAX_ENDPOINTS: Final[int] = 10_000
MAX_CLOCK_SKEW_SECONDS: Final[int] = 5

_PUT_LUA: Final[str] = """
local function compare_decimal(left, right)
    left = string.gsub(left, '^0+', '')
    right = string.gsub(right, '^0+', '')
    if left == '' then left = '0' end
    if right == '' then right = '0' end
    if string.len(left) < string.len(right) then return -1 end
    if string.len(left) > string.len(right) then return 1 end
    if left < right then return -1 end
    if left > right then return 1 end
    return 0
end

local function compare_integer(left, right)
    local left_negative = string.sub(left, 1, 1) == '-'
    local right_negative = string.sub(right, 1, 1) == '-'
    if left_negative ~= right_negative then
        return left_negative and -1 or 1
    end
    if left_negative then
        return -compare_decimal(string.sub(left, 2), string.sub(right, 2))
    end
    return compare_decimal(left, right)
end

local redis_time = redis.call('TIME')
local redis_now = tonumber(redis_time[1]) + tonumber(redis_time[2]) / 1000000
local redis_now_micros = tonumber(redis_time[1]) * 1000000 + tonumber(redis_time[2])
local observed_micros = tonumber(ARGV[4])
if not observed_micros or observed_micros > redis_now_micros + tonumber(ARGV[8]) * 1000000 then
    return -2
end

local expired = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', redis_now, 'LIMIT', 0, ARGV[6])
for _, member in ipairs(expired) do
    redis.call('HDEL', KEYS[1], member)
    redis.call('ZREM', KEYS[2], member)
    redis.call('ZREM', KEYS[3], member)
end

local stored = redis.call('HGET', KEYS[1], ARGV[1])
if not stored and redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[7]) then
    return -1
end
local stored_expiry = redis.call('ZSCORE', KEYS[3], ARGV[1])
if stored and stored_expiry and tonumber(stored_expiry) > redis_now then
    local stored_version, stored_time = string.match(stored, '^(%d+)|(%-?%d+)|%d+|%d+$')
    if stored_version then
        local version_order = compare_decimal(ARGV[3], stored_version)
        local time_order = compare_integer(ARGV[4], stored_time)
        if version_order < 0 or (version_order == 0 and time_order <= 0) then
            return 0
        end
    end
end

local expiry_micros = redis_now_micros + tonumber(ARGV[5]) * 1000000
local packed = ARGV[3] .. '|' .. ARGV[4] .. '|' .. ARGV[2] .. '|' .. string.format('%.0f', expiry_micros)
redis.call('HSET', KEYS[1], ARGV[1], packed)
redis.call('ZADD', KEYS[2], 0, ARGV[1])
redis.call('ZADD', KEYS[3], redis_now + tonumber(ARGV[5]), ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[5])
redis.call('EXPIRE', KEYS[2], ARGV[5])
redis.call('EXPIRE', KEYS[3], ARGV[5])
return 1
"""

_CLEAN_LUA: Final[str] = """
local removed = 0
for offset = 1, #ARGV, 3 do
    local member = ARGV[offset]
    local expected = ARGV[offset + 1]
    local mode = ARGV[offset + 2]
    local remove = false
    if mode == 'missing' then
        remove = not redis.call('HGET', KEYS[1], member)
    elseif mode == 'invalid' then
        remove = redis.call('HGET', KEYS[1], member) == expected
    end
    if remove then
        redis.call('HDEL', KEYS[1], member)
        redis.call('ZREM', KEYS[2], member)
        redis.call('ZREM', KEYS[3], member)
        removed = removed + 1
    end
end
return removed
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class TipKeys:
    values: str
    index: str
    expiry: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreValue:
    key: str
    value: int
    version: int
    observed_at: datetime
    expiry_micros: int
    raw: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _Cleanup:
    member: str
    expected: str
    mode: str


def _to_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes | bytearray):
        try:
            return bytes(value).decode()
        except UnicodeDecodeError:
            return None
    return None


def _to_int(value: object, *, signed: bool = False) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = _to_text(value)
    if text is None:
        return None
    digits = text
    if signed and text.startswith('-'):
        digits = text[1:]
    if not digits or not digits.isascii() or not digits.isdecimal():
        return None
    return int(text)


def _redis_micros(value: object) -> int:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise RuntimeError('Redis returned an invalid tip time.')
    seconds = _to_int(value[0])
    micros = _to_int(value[1])
    if seconds is None or seconds < 0 or micros is None or not 0 <= micros < 1_000_000:
        raise RuntimeError('Redis returned an invalid tip time.')
    return seconds * 1_000_000 + micros


def _parse_value(member: str, raw: object) -> StoreValue | None:
    packed = _to_text(raw)
    if packed is None:
        return None
    parts = packed.split('|')
    if len(parts) != 4:
        return None
    version = _to_int(parts[0])
    observed_micros = _to_int(parts[1], signed=True)
    tip_value = _to_int(parts[2])
    expiry_micros = _to_int(parts[3])
    if tip_value is None or version is None or observed_micros is None or expiry_micros is None:
        return None
    try:
        observed_at = datetime.fromtimestamp(observed_micros / 1_000_000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return StoreValue(
        key=member,
        value=tip_value,
        version=version,
        observed_at=observed_at,
        expiry_micros=expiry_micros,
        raw=packed,
    )


def _write_result(value: object) -> TipWriteResult:
    code = _to_int(value, signed=True)
    if code == 1:
        return TipWriteResult.STORED
    if code == 0:
        return TipWriteResult.STALE_NOOP
    if code == -1:
        return TipWriteResult.CAPACITY_REJECTED
    if code == -2:
        return TipWriteResult.FUTURE_REJECTED
    raise RuntimeError('Redis returned an invalid tip write result.')


class TipStore:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._put = redis_client.register_script(_PUT_LUA)
        self._clean = redis_client.register_script(_CLEAN_LUA)

    async def put(
        self,
        *,
        keys: TipKeys,
        key: str,
        value: int,
        version: int,
        observed_at: datetime,
        ttl_seconds: int,
    ) -> TipWriteResult:
        """Atomically classify and store one observation against Redis time and dimension capacity."""
        observed_micros = to_epoch_micros(observed_at)
        result = await self._put(
            keys=[keys.values, keys.index, keys.expiry],
            args=[
                key,
                value,
                version,
                observed_micros,
                ttl_seconds,
                PUT_CLEANUP_LIMIT,
                MAX_ENDPOINTS,
                MAX_CLOCK_SKEW_SECONDS,
            ],
        )
        return _write_result(result)

    async def get(self, *, keys: TipKeys, key: str) -> StoreValue | None:
        async with self._redis.pipeline(transaction=False) as pipeline:
            pipeline.time()
            pipeline.hget(keys.values, key)
            raw_time, raw = await pipeline.execute()
        now_micros = _redis_micros(raw_time)
        value = _parse_value(key, raw)
        if value is not None and value.expiry_micros > now_micros:
            return value
        mode = 'missing' if raw is None else 'invalid'
        expected = _to_text(raw) or ''
        await self._cleanup(keys=keys, items=[_Cleanup(member=key, expected=expected, mode=mode)])
        return None

    async def iterate(self, keys: TipKeys) -> AsyncIterator[StoreValue]:
        """Yield at most 256 lexically stable members per Redis read page."""
        boundary = '-'
        while True:
            # Reason: redis.asyncio commands are awaitable at runtime; stubs include a sync branch.
            members = await self._redis.zrangebylex(  # pyright: ignore[reportGeneralTypeIssues]
                keys.index,
                boundary,
                '+',
                start=0,
                num=READ_PAGE_SIZE,
            )
            if not members:
                return
            member_names = [_to_text(member) for member in members]
            if any(member is None for member in member_names):
                raise RuntimeError('Tip index contains an invalid member.')
            names = [member for member in member_names if member is not None]
            async with self._redis.pipeline(transaction=False) as pipeline:
                pipeline.time()
                pipeline.hmget(keys.values, names)
                raw_time, rows = await pipeline.execute()
            now_micros = _redis_micros(raw_time)
            cleanup: list[_Cleanup] = []
            values: list[StoreValue] = []
            for member, raw in zip(names, rows, strict=True):
                parsed = _parse_value(member, raw)
                if parsed is None or parsed.expiry_micros <= now_micros:
                    mode = 'missing' if raw is None else 'invalid'
                    cleanup.append(_Cleanup(member=member, expected=_to_text(raw) or '', mode=mode))
                    continue
                values.append(parsed)
            if cleanup:
                await self._cleanup(keys=keys, items=cleanup)
            for value in values:
                yield value
            if len(names) < READ_PAGE_SIZE:
                return
            boundary = f'({names[-1]}'

    async def list(self, keys: TipKeys) -> list[StoreValue]:
        return [value async for value in self.iterate(keys)]

    async def delete_value(self, *, value: StoreValue, keys: TipKeys) -> bool:
        """Delete a value only while Redis still contains the revision the caller inspected."""
        result = await self._cleanup(
            keys=keys,
            items=[_Cleanup(member=value.key, expected=value.raw, mode='invalid')],
        )
        return result == 1

    async def _cleanup(self, *, keys: TipKeys, items: Sequence[_Cleanup]) -> int:
        if not items:
            return 0
        if len(items) > READ_PAGE_SIZE:
            raise ValueError('Tip cleanup batch exceeds the read page size.')
        args: list[str] = []
        for item in items:
            args.extend((item.member, item.expected, item.mode))
        result = await self._clean(keys=[keys.values, keys.index, keys.expiry], args=args)
        return int(result or 0)
