import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from redis.asyncio import Redis

from app.core.config import CONF
from app.util import redis_key

DELETE_IF_VALUE_SCRIPT: Final[str] = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""

OWNED_IF_VALUE_SCRIPT: Final[str] = """
return redis.call('GET', KEYS[1]) == ARGV[1] and 1 or 0
"""

RENEW_IF_VALUE_SCRIPT: Final[str] = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return 1
end
return 0
"""


@dataclass(frozen=True, slots=True)
class RedisLease:
    redis: Redis
    key: str
    token: str
    ttl_seconds: int

    async def owned(self) -> bool:
        # Reason: redis.asyncio eval is awaitable at runtime; stubs include a sync branch.
        result = await self.redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            OWNED_IF_VALUE_SCRIPT,
            1,
            self.key,
            self.token,
        )
        return int(result or 0) == 1

    async def renew(self) -> bool:
        # Reason: redis.asyncio eval is awaitable at runtime; stubs include a sync branch.
        result = await self.redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            RENEW_IF_VALUE_SCRIPT,
            1,
            self.key,
            self.token,
            self.ttl_seconds,
        )
        return int(result or 0) == 1

    async def release(self) -> bool:
        return await delete_string_if_value(self.redis, self.key, self.token)


def build_key(*parts: str) -> str:
    return redis_key.join_key(CONF.PROJECT_NAME, *parts)


def build_pattern(*parts: str) -> str:
    return redis_key.join_pattern(CONF.PROJECT_NAME, *parts)


def build_prefix(*parts: str) -> str:
    return redis_key.join_prefix(CONF.PROJECT_NAME, *parts)


async def delete_keys_matching(redis: Redis, pattern: str, *, batch_size: int = 1000) -> int:
    """Delete Redis keys matched by a scan pattern without blocking on KEYS."""
    keys: list[str] = []
    deleted = 0
    async for key in redis.scan_iter(match=pattern, count=batch_size):
        keys.append(str(key))
        if len(keys) >= batch_size:
            deleted += await redis.delete(*keys)
            keys.clear()
    if keys:
        deleted += await redis.delete(*keys)
    return deleted


async def delete_string_if_value(redis: Redis, key: str, value: str) -> bool:
    """Delete a Redis string key only when its stored value matches."""
    # Reason: redis.asyncio eval is awaitable at runtime; stubs include a sync branch.
    result = await redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
        DELETE_IF_VALUE_SCRIPT,
        1,
        key,
        value,
    )
    return int(result or 0) == 1


async def acquire_redis_lease(redis: Redis, key: str, *, ttl_seconds: int) -> RedisLease | None:
    token = secrets.token_urlsafe(16)
    # Reason: redis.asyncio set is awaitable at runtime; stubs include a sync branch.
    acquired = await redis.set(key, token, ex=ttl_seconds, nx=True)  # pyright: ignore[reportGeneralTypeIssues]
    if not acquired:
        return None
    return RedisLease(redis=redis, key=key, token=token, ttl_seconds=ttl_seconds)


@asynccontextmanager
async def hold_redis_token_lease(redis: Redis, key: str, *, ttl_seconds: int) -> AsyncGenerator[RedisLease | None]:
    """Acquire a token-aware Redis lease and release it only while still owned."""
    lease = await acquire_redis_lease(redis, key, ttl_seconds=ttl_seconds)
    try:
        yield lease
    finally:
        if lease is not None:
            await lease.release()
