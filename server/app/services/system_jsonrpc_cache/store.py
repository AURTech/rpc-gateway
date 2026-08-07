import asyncio
import base64
from datetime import UTC, datetime
from typing import Final

import orjson
from redis.asyncio import Redis
from tortoise import connections

from app.infra import redis
from app.model.blockchain import Chain
from app.model.system_jsonrpc_cache import CacheEntry, CacheFlightLease, CacheKey, CachePolicy, CacheTier
from app.services.system_jsonrpc_cache.codec import PayloadCodec
from app.services.system_jsonrpc_cache.flight import flight_key, flight_value
from app.services.system_jsonrpc_cache.interface import RetentionDeleteResult
from app.services.system_jsonrpc_cache.limits import REDIS_IO_TIMEOUT_SECONDS
from app.util.datetime import to_epoch_millis

_GET_PAYLOAD: Final[str] = """
SELECT payload, payload_size, stored_size, sequence, fresh_until, stale_until
FROM system_jsonrpc_cache_payload
WHERE chain = $1 AND network = $2 AND method = $3 AND cache_key = $4
  AND stored_at >= NOW() - ($5::bigint * INTERVAL '1 second')
"""

_COMMIT_PAYLOAD: Final[str] = """
WITH owned AS MATERIALIZED (
    SELECT lease.fence
    FROM system_jsonrpc_cache_payload_lease AS lease
    WHERE lease.chain = $1 AND lease.network = $2 AND lease.method = $3 AND lease.cache_key = $4
      AND lease.fence = $11 AND lease.token = $12 AND lease.lease_until > clock_timestamp()
    FOR UPDATE
)
INSERT INTO system_jsonrpc_cache_payload (
    chain, network, method, cache_key, sequence, payload, payload_size, stored_size,
    fresh_until, stale_until, publisher_fence, stored_at
)
SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, owned.fence, NOW()
FROM owned
ON CONFLICT (chain, network, method, cache_key) DO UPDATE SET
    sequence = EXCLUDED.sequence,
    payload = EXCLUDED.payload,
    payload_size = EXCLUDED.payload_size,
    stored_size = EXCLUDED.stored_size,
    fresh_until = EXCLUDED.fresh_until,
    stale_until = EXCLUDED.stale_until,
    publisher_fence = EXCLUDED.publisher_fence,
    stored_at = EXCLUDED.stored_at
WHERE system_jsonrpc_cache_payload.publisher_fence <= EXCLUDED.publisher_fence
RETURNING publisher_fence
"""

_COMMIT_REFRESH_PAYLOAD: Final[str] = """
WITH owned AS MATERIALIZED (
    SELECT lease.fence
    FROM system_jsonrpc_cache_payload_lease AS lease
    WHERE lease.chain = $1 AND lease.network = $2 AND lease.method = $3 AND lease.cache_key = $4
      AND lease.fence = $7 AND lease.token = $8 AND lease.lease_until > clock_timestamp()
    FOR UPDATE
)
UPDATE system_jsonrpc_cache_payload
SET fresh_until = $5, stale_until = $6, publisher_fence = owned.fence
FROM owned
WHERE system_jsonrpc_cache_payload.chain = $1
  AND system_jsonrpc_cache_payload.network = $2
  AND system_jsonrpc_cache_payload.method = $3
  AND system_jsonrpc_cache_payload.cache_key = $4
  AND system_jsonrpc_cache_payload.publisher_fence <= owned.fence
RETURNING system_jsonrpc_cache_payload.publisher_fence
"""

_COMMIT_REDIS_TTL: Final[str] = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
local existing_raw = redis.call('GET', KEYS[2])
if existing_raw then
    local decoded, existing = pcall(cjson.decode, existing_raw)
    if decoded and tonumber(existing.publisher_fence or 0) > tonumber(ARGV[2]) then
        return 0
    end
end
redis.call('SET', KEYS[2], ARGV[3], 'PX', ARGV[4])
return 1
"""

_DELETE_EXPIRED_PAYLOADS: Final[str] = """
WITH payload_candidates AS MATERIALIZED (
    SELECT payload.id, payload.stored_size, payload.stored_at
    FROM system_jsonrpc_cache_payload AS payload
    WHERE payload.chain = $1
      AND payload.stored_at < NOW() - ($2::bigint * INTERVAL '1 second')
    ORDER BY payload.stored_at, payload.id
    LIMIT $3::integer + 1
), ranked_payloads AS MATERIALIZED (
    SELECT
        candidate.id,
        candidate.stored_at,
        ROW_NUMBER() OVER (ORDER BY candidate.stored_at, candidate.id) AS row_number,
        SUM(candidate.stored_size::bigint) OVER (ORDER BY candidate.stored_at, candidate.id) AS cumulative_bytes
    FROM payload_candidates AS candidate
), payload_victim_ids AS MATERIALIZED (
    SELECT ranked.id
    FROM ranked_payloads AS ranked
    WHERE ranked.row_number <= $3
      AND (ranked.row_number = 1 OR ranked.cumulative_bytes <= $4::bigint)
), payload_victims AS (
    SELECT payload.ctid
    FROM system_jsonrpc_cache_payload AS payload
    JOIN payload_victim_ids AS victim ON victim.id = payload.id
    ORDER BY payload.stored_at, payload.id
    FOR UPDATE OF payload SKIP LOCKED
), deleted AS (
    DELETE FROM system_jsonrpc_cache_payload AS payload
    USING payload_victims AS victim
    WHERE payload.ctid = victim.ctid
    RETURNING payload.chain, payload.network, payload.method, payload.cache_key, payload.stored_size
), deleted_payload_leases AS (
    DELETE FROM system_jsonrpc_cache_payload_lease AS lease
    USING deleted
    WHERE lease.chain = deleted.chain
      AND lease.network = deleted.network
      AND lease.method = deleted.method
      AND lease.cache_key = deleted.cache_key
      AND lease.lease_until <= clock_timestamp()
), orphan_lease_pending AS MATERIALIZED (
    SELECT lease.id, lease.lease_until
    FROM system_jsonrpc_cache_payload_lease AS lease
    WHERE lease.chain = $1
      AND lease.lease_until < NOW() - ($2::bigint * INTERVAL '1 second')
      AND NOT EXISTS (
          SELECT 1
          FROM system_jsonrpc_cache_payload AS payload
          WHERE payload.chain = lease.chain
            AND payload.network = lease.network
            AND payload.method = lease.method
            AND payload.cache_key = lease.cache_key
    )
    ORDER BY lease.lease_until, lease.id
    LIMIT $3::integer + 1
), orphan_lease_candidates AS MATERIALIZED (
    SELECT lease.id, lease.lease_until
    FROM system_jsonrpc_cache_payload_lease AS lease
    WHERE lease.chain = $1
      AND lease.lease_until < NOW() - ($2::bigint * INTERVAL '1 second')
      AND NOT EXISTS (
          SELECT 1
          FROM system_jsonrpc_cache_payload AS payload
          WHERE payload.chain = lease.chain
            AND payload.network = lease.network
            AND payload.method = lease.method
            AND payload.cache_key = lease.cache_key
      )
    ORDER BY lease.lease_until, lease.id
    LIMIT $3::integer + 1
    FOR UPDATE OF lease SKIP LOCKED
), orphan_lease_victim_ids AS MATERIALIZED (
    SELECT candidate.id
    FROM orphan_lease_candidates AS candidate
    ORDER BY candidate.lease_until, candidate.id
    LIMIT $3
), orphan_lease_victims AS (
    SELECT lease.ctid
    FROM system_jsonrpc_cache_payload_lease AS lease
    JOIN orphan_lease_victim_ids AS victim ON victim.id = lease.id
    ORDER BY lease.lease_until, lease.id
), deleted_orphan_leases AS (
    DELETE FROM system_jsonrpc_cache_payload_lease AS lease
    USING orphan_lease_victims AS victim
    WHERE lease.ctid = victim.ctid
    RETURNING lease.id
)
SELECT
    COUNT(*)::bigint AS deleted_rows,
    COALESCE(SUM(stored_size), 0)::bigint AS deleted_bytes,
    (
        (SELECT COUNT(*) FROM payload_candidates) > COUNT(*)
        OR (SELECT COUNT(*) FROM orphan_lease_pending) > (SELECT COUNT(*) FROM deleted_orphan_leases)
    ) AS has_more
FROM deleted
"""


def _redis_ttl_key(key: CacheKey) -> str:
    return redis.build_key(
        'system_jsonrpc_cache',
        'v1',
        'redis_ttl',
        key.chain.value,
        key.network.value,
        key.method,
        key.digest,
    )


class RedisTtlStore:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._commit = redis_client.register_script(_COMMIT_REDIS_TTL)

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        async with asyncio.timeout(REDIS_IO_TIMEOUT_SECONDS):
            raw = await self._redis.get(_redis_ttl_key(policy.key))
        if not isinstance(raw, str | bytes):
            return None
        try:
            data = orjson.loads(raw)
            payload = base64.b64decode(data['payload'], validate=True)
            fresh_until = datetime.fromtimestamp(data['fresh_until_ms'] / 1000, tz=UTC)
            stale_until = datetime.fromtimestamp(data['stale_until_ms'] / 1000, tz=UTC)
        except (KeyError, TypeError, ValueError, OverflowError, orjson.JSONDecodeError):
            return None
        return CacheEntry(
            key=policy.key,
            tier=CacheTier.REDIS_TTL,
            payload=payload,
            fresh_until=fresh_until,
            stale_until=stale_until,
            sequence=None,
        )

    @staticmethod
    def _value(entry: CacheEntry, *, publisher_fence: int) -> tuple[bytes, int]:
        if entry.fresh_until is None or entry.stale_until is None:
            raise ValueError('Redis TTL cache entries require freshness boundaries.')
        ttl_ms = max(1, to_epoch_millis(entry.stale_until) - to_epoch_millis(datetime.now(UTC)))
        value = orjson.dumps(
            {
                'fresh_until_ms': to_epoch_millis(entry.fresh_until),
                'stale_until_ms': to_epoch_millis(entry.stale_until),
                'publisher_fence': publisher_fence,
                'payload': base64.b64encode(entry.payload).decode(),
            }
        )
        return value, ttl_ms

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        del refresh
        value, ttl_ms = self._value(entry, publisher_fence=lease.fence)
        async with asyncio.timeout(REDIS_IO_TIMEOUT_SECONDS):
            applied = await self._commit(
                keys=[flight_key(entry.key), _redis_ttl_key(entry.key)],
                args=[flight_value(lease), lease.fence, value, ttl_ms],
            )
        return int(applied or 0) == 1


class PostgresRetentionStore:
    def __init__(self, connection_name: str = 'default', *, codec: PayloadCodec | None = None) -> None:
        if not connection_name:
            raise ValueError('PostgreSQL retention connection name cannot be empty.')
        self._connection_name = connection_name
        self._codec = codec or PayloadCodec()

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        retention_seconds = policy.retention_seconds
        if retention_seconds is None:
            raise ValueError('PostgreSQL retention policies require a retention period.')
        connection = connections.get(self._connection_name)
        rows = await connection.execute_query_dict(
            _GET_PAYLOAD,
            [policy.key.chain.value, policy.key.network.value, policy.key.method, policy.key.digest, retention_seconds],
        )
        if not rows:
            return None
        payload = rows[0].get('payload')
        payload_size = rows[0].get('payload_size')
        stored_size = rows[0].get('stored_size')
        if (
            not isinstance(payload, bytes | bytearray | memoryview)
            or not isinstance(payload_size, int)
            or not isinstance(stored_size, int)
            or stored_size != len(payload)
        ):
            return None
        raw_payload = await self._codec.decompress(bytes(payload), expected_size=payload_size)
        fresh_until = rows[0].get('fresh_until')
        stale_until = rows[0].get('stale_until')
        return CacheEntry(
            key=policy.key,
            tier=CacheTier.POSTGRES_RETENTION,
            payload=raw_payload,
            fresh_until=fresh_until if isinstance(fresh_until, datetime) else None,
            stale_until=stale_until if isinstance(stale_until, datetime) else None,
            sequence=rows[0].get('sequence') if isinstance(rows[0].get('sequence'), int) else None,
        )

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        connection = connections.get(self._connection_name)
        if refresh:
            rows = await connection.execute_query_dict(
                _COMMIT_REFRESH_PAYLOAD,
                [
                    entry.key.chain.value,
                    entry.key.network.value,
                    entry.key.method,
                    entry.key.digest,
                    entry.fresh_until,
                    entry.stale_until,
                    lease.fence,
                    lease.token,
                ],
            )
        else:
            payload = await self._codec.compress(entry.payload)
            rows = await connection.execute_query_dict(
                _COMMIT_PAYLOAD,
                [
                    entry.key.chain.value,
                    entry.key.network.value,
                    entry.key.method,
                    entry.key.digest,
                    entry.sequence,
                    payload,
                    len(entry.payload),
                    len(payload),
                    entry.fresh_until,
                    entry.stale_until,
                    lease.fence,
                    lease.token,
                ],
            )
        return bool(rows)

    async def delete_expired(
        self,
        chain: Chain,
        retention_seconds: int,
        *,
        max_rows: int,
        max_bytes: int,
    ) -> RetentionDeleteResult:
        if isinstance(max_rows, bool) or not 1 <= max_rows <= 1000:
            raise ValueError('PostgreSQL retention cleanup limit must be between 1 and 1000.')
        if isinstance(max_bytes, bool) or max_bytes < 1:
            raise ValueError('PostgreSQL retention cleanup byte limit must be positive.')
        if isinstance(retention_seconds, bool) or retention_seconds < 1:
            raise ValueError('PostgreSQL retention must be positive.')
        connection = connections.get(self._connection_name)
        rows = await connection.execute_query_dict(
            _DELETE_EXPIRED_PAYLOADS,
            [chain.value, retention_seconds, max_rows, max_bytes],
        )
        if not rows:
            raise RuntimeError('PostgreSQL retention cleanup returned no result.')
        deleted_rows = rows[0].get('deleted_rows')
        deleted_bytes = rows[0].get('deleted_bytes')
        has_more = rows[0].get('has_more')
        if not isinstance(deleted_rows, int) or not isinstance(deleted_bytes, int) or not isinstance(has_more, bool):
            raise RuntimeError('PostgreSQL retention cleanup returned an invalid result.')
        return RetentionDeleteResult(deleted_rows=deleted_rows, deleted_bytes=deleted_bytes, has_more=has_more)


class HybridSystemJsonRpcCacheStore:
    def __init__(self, redis_ttl: RedisTtlStore, postgres_retention: PostgresRetentionStore) -> None:
        self._redis_ttl = redis_ttl
        self._postgres_retention = postgres_retention

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        if policy.tier is CacheTier.REDIS_TTL:
            return await self._redis_ttl.get(policy)
        return await self._postgres_retention.get(policy)

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        if entry.tier is CacheTier.REDIS_TTL:
            return await self._redis_ttl.commit(entry, lease, refresh=refresh)
        return await self._postgres_retention.commit(entry, lease, refresh=refresh)
