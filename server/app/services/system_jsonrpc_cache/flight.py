import asyncio
import secrets
import time
from typing import Final

from redis.asyncio import Redis
from tortoise import connections

from app.infra import redis
from app.model.system_jsonrpc_cache import CacheFlightLease, CacheKey

_ACQUIRE_LUA: Final[str] = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return '0'
end
local redis_time = redis.call('TIME')
local fence = tonumber(redis_time[1]) * 1000000 + tonumber(redis_time[2])
local allocated = tonumber(redis.call('GET', KEYS[2]) or '0')
if fence <= allocated then
    fence = allocated + 1
end
local fence_value = string.format('%.0f', fence)
redis.call('SET', KEYS[2], fence_value)
redis.call('SET', KEYS[1], fence_value .. ':' .. ARGV[1], 'PX', ARGV[2])
return fence_value
"""

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_ACQUIRE_RETENTION: Final[str] = """
INSERT INTO system_jsonrpc_cache_payload_lease (
    chain, network, method, cache_key, token, fence, lease_until
)
VALUES ($1, $2, $3, $4, $5, 1, clock_timestamp() + ($6::bigint * INTERVAL '1 millisecond'))
ON CONFLICT (chain, network, method, cache_key) DO UPDATE SET
    token = EXCLUDED.token,
    fence = system_jsonrpc_cache_payload_lease.fence + 1,
    lease_until = EXCLUDED.lease_until
WHERE system_jsonrpc_cache_payload_lease.lease_until <= clock_timestamp()
RETURNING fence
"""

_RENEW_RETENTION: Final[str] = """
UPDATE system_jsonrpc_cache_payload_lease
SET lease_until = clock_timestamp() + ($7::bigint * INTERVAL '1 millisecond')
WHERE chain = $1 AND network = $2 AND method = $3 AND cache_key = $4
  AND token = $5 AND fence = $6 AND lease_until > clock_timestamp()
RETURNING fence
"""

_RELEASE_RETENTION: Final[str] = """
UPDATE system_jsonrpc_cache_payload_lease
SET lease_until = clock_timestamp()
WHERE chain = $1 AND network = $2 AND method = $3 AND cache_key = $4
  AND token = $5 AND fence = $6
"""

_RETENTION_ACTIVE: Final[str] = """
SELECT EXISTS (
    SELECT 1
    FROM system_jsonrpc_cache_payload_lease
    WHERE chain = $1 AND network = $2 AND method = $3 AND cache_key = $4
      AND lease_until > clock_timestamp()
) AS active
"""


def flight_key(key: CacheKey) -> str:
    return redis.build_key(
        'system_jsonrpc_cache',
        'v1',
        'flight',
        key.chain.value,
        key.network.value,
        key.method,
        key.digest,
    )


def _fence_key() -> str:
    return redis.build_key('system_jsonrpc_cache', 'v1', 'fence')


def flight_value(lease: CacheFlightLease) -> str:
    return f'{lease.fence}:{lease.token}'


class RedisTtlFlight:
    def __init__(self, redis_client: Redis, *, lease_ms: int, io_timeout_seconds: float = 1) -> None:
        if isinstance(lease_ms, bool) or not 1000 <= lease_ms <= 120_000:
            raise ValueError('System JSON-RPC Cache flight lease must be between 1000 and 120000 milliseconds.')
        if isinstance(io_timeout_seconds, bool) or not 0.05 <= io_timeout_seconds <= 5:
            raise ValueError('System JSON-RPC Cache Redis I/O timeout must be between 0.05 and 5 seconds.')
        self._redis = redis_client
        self._lease_ms = lease_ms
        self._io_timeout_seconds = io_timeout_seconds
        self._acquire = redis_client.register_script(_ACQUIRE_LUA)
        self._release = redis_client.register_script(_RELEASE_LUA)
        self._renew = redis_client.register_script(_RENEW_LUA)

    async def acquire(self, key: CacheKey) -> CacheFlightLease | None:
        token = secrets.token_urlsafe(18)
        async with asyncio.timeout(self._io_timeout_seconds):
            raw_fence = await self._acquire(
                keys=[flight_key(key), _fence_key()],
                args=[token, self._lease_ms],
            )
        fence = int(raw_fence or 0)
        return CacheFlightLease(token=token, fence=fence) if fence > 0 else None

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        async with asyncio.timeout(self._io_timeout_seconds):
            result = await self._renew(keys=[flight_key(key)], args=[flight_value(lease), self._lease_ms])
        return int(result or 0) == 1

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        async with asyncio.timeout(self._io_timeout_seconds):
            await self._release(keys=[flight_key(key)], args=[flight_value(lease)])

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        delay = 0.02
        while time.monotonic() < deadline:
            remaining_seconds = deadline - time.monotonic()
            async with asyncio.timeout(min(self._io_timeout_seconds, remaining_seconds)):
                exists = await self._redis.exists(flight_key(key))
            if not exists:
                return True
            await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay = min(delay * 2, 1.0)
        return False


class PostgresRetentionFlight:
    """Coordinate retained PostgreSQL loaders so ownership and publication share one authority."""

    def __init__(self, *, lease_ms: int, io_timeout_seconds: float = 1, connection_name: str = 'default') -> None:
        if isinstance(lease_ms, bool) or not 1000 <= lease_ms <= 120_000:
            raise ValueError('System JSON-RPC Cache flight lease must be between 1000 and 120000 milliseconds.')
        if isinstance(io_timeout_seconds, bool) or not 0.05 <= io_timeout_seconds <= 5:
            raise ValueError('System JSON-RPC Cache PostgreSQL I/O timeout must be between 0.05 and 5 seconds.')
        if not connection_name:
            raise ValueError('PostgreSQL coordination connection name cannot be empty.')
        self._lease_ms = lease_ms
        self._io_timeout_seconds = io_timeout_seconds
        self._connection_name = connection_name

    async def acquire(self, key: CacheKey) -> CacheFlightLease | None:
        token = secrets.token_urlsafe(18)
        connection = connections.get(self._connection_name)
        async with asyncio.timeout(self._io_timeout_seconds):
            rows = await connection.execute_query_dict(
                _ACQUIRE_RETENTION,
                [key.chain.value, key.network.value, key.method, key.digest, token, self._lease_ms],
            )
        if not rows:
            return None
        fence = rows[0].get('fence')
        if not isinstance(fence, int) or fence <= 0:
            raise RuntimeError('System JSON-RPC Cache PostgreSQL retention lease returned an invalid fence.')
        return CacheFlightLease(token=token, fence=fence)

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        connection = connections.get(self._connection_name)
        async with asyncio.timeout(self._io_timeout_seconds):
            rows = await connection.execute_query_dict(
                _RENEW_RETENTION,
                [
                    key.chain.value,
                    key.network.value,
                    key.method,
                    key.digest,
                    lease.token,
                    lease.fence,
                    self._lease_ms,
                ],
            )
        return bool(rows)

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        connection = connections.get(self._connection_name)
        async with asyncio.timeout(self._io_timeout_seconds):
            await connection.execute_query(
                _RELEASE_RETENTION,
                [key.chain.value, key.network.value, key.method, key.digest, lease.token, lease.fence],
            )

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        delay = 0.02
        connection = connections.get(self._connection_name)
        while time.monotonic() < deadline:
            remaining_seconds = deadline - time.monotonic()
            async with asyncio.timeout(min(self._io_timeout_seconds, remaining_seconds)):
                rows = await connection.execute_query_dict(
                    _RETENTION_ACTIVE,
                    [key.chain.value, key.network.value, key.method, key.digest],
                )
            active = rows[0].get('active') if rows else None
            if active is not True:
                return True
            await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay = min(delay * 2, 1.0)
        return False
