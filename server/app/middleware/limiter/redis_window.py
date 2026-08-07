import hashlib
import secrets
from dataclasses import dataclass
from typing import Final

from app.infra.redis import build_key
from pyrate_limiter import Rate
from redis.asyncio import Redis

RATE_LIMIT_KEY_TTL_BUFFER_MS: Final[int] = 1000
REDIS_SLIDING_WINDOW_SCRIPT: Final[str] = """
local key = KEYS[1]
local member = ARGV[1]
local rates_count = tonumber(ARGV[2])
local max_interval = tonumber(ARGV[3])
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)

redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - max_interval)

local allowed = 1
local retry_after_ms = 0
for index = 1,rates_count do
    local offset = 4 + (index - 1) * 2
    local limit = tonumber(ARGV[offset])
    local interval = tonumber(ARGV[offset + 1])
    local lower_bound = now_ms - interval
    local count = redis.call('ZCOUNT', key, '(' .. lower_bound, now_ms)
    if count >= limit then
        allowed = 0
        local release_offset = count - limit
        local release_item = redis.call(
            'ZRANGEBYSCORE',
            key,
            '(' .. lower_bound,
            now_ms,
            'WITHSCORES',
            'LIMIT',
            release_offset,
            1
        )
        if release_item[2] then
            local wait_ms = math.max(1, math.ceil(tonumber(release_item[2]) + interval - now_ms))
            retry_after_ms = math.max(retry_after_ms, wait_ms)
        end
    end
end

if allowed == 1 then
    redis.call('ZADD', key, now_ms, member)
    redis.call('PEXPIRE', key, max_interval + tonumber(ARGV[4 + rates_count * 2]))
end

return {allowed, retry_after_ms}
"""


@dataclass(frozen=True, slots=True)
class RedisSlidingWindowResult:
    allowed: bool
    retry_after_ms: int


def _scope_digest(parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        value = part.encode()
        digest.update(len(value).to_bytes(8, byteorder='big'))
        digest.update(value)
    return digest.hexdigest()


class RedisSlidingWindowStore:
    """Persist independently keyed sliding-window counters in Redis.

    Redis server time and one Lua execution make cleanup, admission, and insertion
    atomic across API replicas. Scope values are hashed before becoming Redis keys.
    """

    def __init__(self, rates: list[Rate], bucket_key: str) -> None:
        if not rates:
            raise ValueError('Redis sliding-window rates cannot be empty.')
        if any(rate.limit < 1 or rate.interval < 1 for rate in rates):
            raise ValueError('Redis sliding-window rates must be positive.')
        self._rates = tuple(rates)
        self._bucket_key = bucket_key
        self._max_interval = max(rate.interval for rate in rates)
        build_key('rate-limit', 'v2', bucket_key, '0' * 64)

    def build_scope_key(self, scope: tuple[str, ...]) -> str:
        if not scope:
            raise ValueError('Redis sliding-window scope cannot be empty.')
        return build_key('rate-limit', 'v2', self._bucket_key, _scope_digest(scope))

    async def acquire(self, redis: Redis, scope: tuple[str, ...]) -> RedisSlidingWindowResult:
        """Consume one permit for a scope using every configured window.

        Raises:
            RedisError: Redis rejects or cannot execute the Lua script.
            ValueError: Redis returns an invalid result.
        """
        key = self.build_scope_key(scope)
        args: list[str | int] = [secrets.token_hex(16), len(self._rates), self._max_interval]
        for rate in self._rates:
            args.extend((rate.limit, rate.interval))
        args.append(RATE_LIMIT_KEY_TTL_BUFFER_MS)
        # Reason: redis.asyncio eval is awaitable at runtime; stubs include a sync branch.
        result = await redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            REDIS_SLIDING_WINDOW_SCRIPT,
            1,
            key,
            *args,
        )
        if not isinstance(result, list) or len(result) != 2:
            raise ValueError('Redis sliding window returned an invalid result.')
        try:
            allowed = int(result[0]) == 1
            retry_after_ms = max(0, int(result[1]))
        except (TypeError, ValueError) as exc:
            raise ValueError('Redis sliding window returned invalid values.') from exc
        return RedisSlidingWindowResult(allowed=allowed, retry_after_ms=retry_after_ms)
