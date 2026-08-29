from typing import Final, TypedDict

from app.core.config import CONF
from app.infra import redis
from app.infra.broker import broker
from app.infra.db import SYSTEM_CACHE_RETENTION_DB_CONNECTION
from app.infra.redis import hold_redis_token_lease
from app.services.base import Manager
from app.services.system_cache.limits import RETENTION_CLEANUP_INTERVAL_SECONDS, RETENTION_CLEANUP_LEASE_SECONDS
from app.services.system_cache.retention import RetentionManager
from app.services.system_cache.store import PostgresRetentionStore
from fastlog import log

_CLEANUP_SCHEDULE: Final[list[dict[str, int]]] = (
    [{'interval': RETENTION_CLEANUP_INTERVAL_SECONDS}] if CONF.SYSTEM_CACHE_ENABLED else []
)


class RetentionCleanupTaskResult(TypedDict):
    status: str
    deleted_rows: int
    deleted_bytes: int
    attempted_batches: int
    completed_batches: int
    timed_out_chains: list[str]
    elapsed_ms: int


def _empty_result(status: str) -> RetentionCleanupTaskResult:
    return {
        'status': status,
        'deleted_rows': 0,
        'deleted_bytes': 0,
        'attempted_batches': 0,
        'completed_batches': 0,
        'timed_out_chains': [],
        'elapsed_ms': 0,
    }


@broker.task(schedule=_CLEANUP_SCHEDULE)
async def delete_expired_retained_entries() -> RetentionCleanupTaskResult:
    lease_key = redis.build_key('system_cache', 'v1', 'retention_cleanup')
    cursor_key = redis.build_key('system_cache', 'v1', 'retention_cleanup_cursor')
    try:
        async with hold_redis_token_lease(
            Manager.redis,
            lease_key,
            ttl_seconds=RETENTION_CLEANUP_LEASE_SECONDS,
        ) as lease:
            if lease is None:
                return _empty_result('busy')
            run_number = await Manager.redis.incr(cursor_key)
            if not isinstance(run_number, int):
                raise RuntimeError('System Cache PostgreSQL cleanup cursor returned an invalid result.')
            manager = RetentionManager(
                PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION),
                CONF.SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN,
                max_batch_bytes=CONF.SYSTEM_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES,
            )
            result = await manager.delete_expired(start_offset=run_number - 1)
    except Exception as exc:
        log.warning(f'System Cache PostgreSQL cleanup failed | Error:{exc!r}')
        return _empty_result('failed')
    timed_out_chains = [chain.value for chain in result.timed_out_chains]
    message = (
        'System Cache PostgreSQL retention entries deleted '
        f'| Rows:{result.deleted_rows} | Bytes:{result.deleted_bytes} '
        f'| AttemptedBatches:{result.attempted_batches} | CompletedBatches:{result.completed_batches} '
        f'| TimedOutChains:{",".join(timed_out_chains)} | ElapsedMs:{result.elapsed_ms}'
    )
    if timed_out_chains:
        log.warning(message)
    elif result.deleted_rows:
        log.info(message)
    return {
        'status': 'partial' if timed_out_chains else 'ok',
        'deleted_rows': result.deleted_rows,
        'deleted_bytes': result.deleted_bytes,
        'attempted_batches': result.attempted_batches,
        'completed_batches': result.completed_batches,
        'timed_out_chains': timed_out_chains,
        'elapsed_ms': result.elapsed_ms,
    }
