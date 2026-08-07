import asyncio
import math
import time
from dataclasses import dataclass
from inspect import isawaitable
from typing import Final

from redis.asyncio import Redis

TOKEN_SCALE: Final[int] = 1_000_000
TOKEN_BUCKET_SCRIPT: Final[str] = """
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local scale = tonumber(ARGV[1])
local states = {}
local allowed = 1
local retry_after_ms = 0

for i, key in ipairs(KEYS) do
    local offset = 2 + (i - 1) * 3
    local rps = tonumber(ARGV[offset])
    local burst = tonumber(ARGV[offset + 1])
    local cost = tonumber(ARGV[offset + 2])
    local capacity = burst * scale
    local cost_tokens = cost * scale
    local refill_per_ms = rps * scale / 1000
    local stored = redis.call('HMGET', key, 'tokens', 'updated_ms')
    local tokens = capacity
    local updated_ms = now_ms

    if stored[1] and stored[2] then
        tokens = math.min(capacity, tonumber(stored[1]) + math.max(0, now_ms - tonumber(stored[2])) * refill_per_ms)
        updated_ms = tonumber(stored[2])
    end

    local bucket_retry_ms = 0
    if tokens < cost_tokens then
        allowed = 0
        bucket_retry_ms = math.ceil((cost_tokens - tokens) / refill_per_ms)
        retry_after_ms = math.max(retry_after_ms, bucket_retry_ms)
    end
    states[i] = {tokens, updated_ms, capacity, cost_tokens, refill_per_ms}
end

if allowed == 1 then
    for i, key in ipairs(KEYS) do
        local state = states[i]
        local remaining = state[1] - state[4]
        local full_after_ms = math.ceil((state[3] - remaining) / state[5])
        local ttl_ms = math.max(60000, full_after_ms + 1000)
        redis.call('HSET', key, 'tokens', remaining, 'updated_ms', now_ms)
        redis.call('PEXPIRE', key, ttl_ms)
    end
end

return {allowed, retry_after_ms}
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenBucketRequest:
    key: str
    rps: float
    burst: int
    cost: int = 1

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError('Token bucket key cannot be empty.')
        if not math.isfinite(self.rps) or self.rps <= 0:
            raise ValueError('Token bucket RPS must be positive and finite.')
        if self.burst < 1:
            raise ValueError('Token bucket burst must be positive.')
        if self.cost < 1:
            raise ValueError('Token bucket cost must be positive.')


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenBucketResult:
    allowed: bool
    retry_after_ms: int = 0
    capacity_limited: bool = False


class RedisTokenBucketStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(TOKEN_BUCKET_SCRIPT)

    async def acquire(self, buckets: tuple[TokenBucketRequest, ...], *, timeout_ms: int) -> TokenBucketResult:
        """Atomically consume every bucket or none of them.

        Raises:
            TimeoutError: Redis does not complete within the configured deadline.
            RedisError: Redis rejects or cannot execute the operation.
            ValueError: Redis returns an invalid result.
        """
        if not buckets:
            return TokenBucketResult(allowed=True)
        keys = [bucket.key for bucket in buckets]
        if len(keys) != len(set(keys)):
            raise ValueError('Token bucket keys must be unique within one acquisition.')
        args: list[int | float] = [TOKEN_SCALE]
        for bucket in buckets:
            args.extend((bucket.rps, bucket.burst, bucket.cost))
        result = self._script(keys=keys, args=args, client=self._redis)
        if isawaitable(result):
            result = await asyncio.wait_for(result, timeout=timeout_ms / 1000)
        if not isinstance(result, list) or len(result) != 2:
            raise ValueError('Redis token bucket returned an invalid result.')
        try:
            allowed = int(result[0]) == 1
            retry_after_ms = max(0, int(result[1]))
        except (TypeError, ValueError) as exc:
            raise ValueError('Redis token bucket returned invalid values.') from exc
        return TokenBucketResult(allowed=allowed, retry_after_ms=retry_after_ms)


@dataclass(slots=True)
class _LocalBucket:
    tokens: float
    updated_at: float
    expires_at: float


class LocalTokenBucketStore:
    def __init__(self, *, max_keys: int) -> None:
        if max_keys < 1:
            raise ValueError('Local token bucket key limit must be positive.')
        self._max_keys = max_keys
        self._items: dict[str, _LocalBucket] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, buckets: tuple[TokenBucketRequest, ...]) -> TokenBucketResult:
        """Atomically consume bounded process-local buckets using a monotonic clock."""
        if not buckets:
            return TokenBucketResult(allowed=True)
        keys = [bucket.key for bucket in buckets]
        if len(keys) != len(set(keys)):
            raise ValueError('Token bucket keys must be unique within one acquisition.')
        async with self._lock:
            return self._acquire_locked(buckets, time.monotonic())

    def _acquire_locked(self, buckets: tuple[TokenBucketRequest, ...], now: float) -> TokenBucketResult:
        self._prune(now)
        missing_keys = {bucket.key for bucket in buckets if bucket.key not in self._items}
        if len(self._items) + len(missing_keys) > self._max_keys:
            return TokenBucketResult(allowed=False, retry_after_ms=1000, capacity_limited=True)

        states: dict[str, _LocalBucket] = {}
        retry_after_ms = 0
        for request in buckets:
            saved = self._items.get(request.key)
            tokens = (
                request.burst if saved is None else min(request.burst, saved.tokens + (now - saved.updated_at) * request.rps)
            )
            refill_seconds = request.burst / request.rps
            state = _LocalBucket(tokens=tokens, updated_at=now, expires_at=now + max(60, refill_seconds + 1))
            states[request.key] = state
            if tokens < request.cost:
                wait_ms = math.ceil((request.cost - tokens) / request.rps * 1000)
                retry_after_ms = max(retry_after_ms, wait_ms)
        if retry_after_ms > 0:
            return TokenBucketResult(allowed=False, retry_after_ms=retry_after_ms)
        for request in buckets:
            state = states[request.key]
            state.tokens -= request.cost
            self._items[request.key] = state
        return TokenBucketResult(allowed=True)

    def _prune(self, now: float) -> None:
        if len(self._items) < self._max_keys:
            return
        expired = [key for key, item in self._items.items() if item.expires_at <= now]
        for key in expired:
            self._items.pop(key, None)
