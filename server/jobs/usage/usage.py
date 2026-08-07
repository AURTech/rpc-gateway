from app.infra.broker import broker
from app.infra.redis import hold_redis_token_lease
from app.services.base import Manager
from app.services.usage import GatewayUsageBuffer, GatewayUsageIngestManager, GatewayUsageRollupManager
from fastlog import log

USAGE_FLUSH_BATCH_SIZE = 500
USAGE_FLUSH_MAX_BATCHES = 20
USAGE_FLUSH_MAX_SECONDS = 5
USAGE_FLUSH_INTERVAL_SECONDS = 5
USAGE_FLUSH_LEASE_SECONDS = 30
USAGE_RETENTION_INTERVAL_SECONDS = 60 * 60
USAGE_RETENTION_LEASE_SECONDS = 45
USAGE_ROLLUP_INTERVAL_SECONDS = 5 * 60
USAGE_ROLLUP_LEASE_SECONDS = 120
USAGE_ROLLUP_MAX_HOURS = 24


@broker.task(schedule=[{'interval': USAGE_FLUSH_INTERVAL_SECONDS}])
async def flush_gateway_usage() -> dict[str, int | float | str | bool | None]:
    result = await GatewayUsageIngestManager.drain(
        batch_size=USAGE_FLUSH_BATCH_SIZE,
        max_batches=USAGE_FLUSH_MAX_BATCHES,
        max_seconds=USAGE_FLUSH_MAX_SECONDS,
        lease_seconds=USAGE_FLUSH_LEASE_SECONDS,
    )
    status = 'ok' if result['lock_acquired'] else 'busy'
    if result['timed_out']:
        log.warning(
            f'Gateway Usage stream drain timed out | Remaining:{result["remaining_entries"]} '
            f'| OldestAge:{result["oldest_age_seconds"]}'
        )
    elif result['limited']:
        log.warning(
            f'Gateway Usage stream reached batch limit | Remaining:{result["remaining_entries"]} '
            f'| OldestAge:{result["oldest_age_seconds"]}'
        )
    return {
        'status': status,
        'lock_acquired': result['lock_acquired'],
        'batches': result['batches'],
        'received': result['received'],
        'inserted': result['inserted'],
        'acknowledged': result['acknowledged'],
        'invalid': result['invalid'],
        'remaining_entries': result['remaining_entries'],
        'oldest_age_seconds': result['oldest_age_seconds'],
        'limited': result['limited'],
        'timed_out': result['timed_out'],
    }


@broker.task(schedule=[{'interval': USAGE_ROLLUP_INTERVAL_SECONDS}])
async def rollup_gateway_usage() -> dict[str, int | str | bool]:
    result = await GatewayUsageRollupManager.rollup(
        limit=USAGE_ROLLUP_MAX_HOURS,
        lease_seconds=USAGE_ROLLUP_LEASE_SECONDS,
    )
    status = 'ok' if result['lock_acquired'] else 'busy'
    if result['rolled_hours']:
        log.info(f'Gateway Usage hours rolled up | Hours:{result["rolled_hours"]}')
    return {
        'status': status,
        'lock_acquired': result['lock_acquired'],
        'rolled_hours': result['rolled_hours'],
    }


@broker.task(schedule=[{'interval': USAGE_RETENTION_INTERVAL_SECONDS}])
async def cleanup_gateway_usage() -> dict[str, int | str | bool]:
    lease_key = GatewayUsageBuffer.retention_lease_key()
    try:
        async with hold_redis_token_lease(
            Manager.redis,
            lease_key,
            ttl_seconds=USAGE_RETENTION_LEASE_SECONDS,
        ) as lease:
            if lease is None:
                return {
                    'status': 'busy',
                    'created_partitions': 0,
                    'dropped_partitions': 0,
                    'deleted_gateway_rows': 0,
                    'deleted_method_rows': 0,
                    'deleted_fine_gateway_rows': 0,
                    'deleted_fine_method_rows': 0,
                }
            result = await GatewayUsageIngestManager.maintain_partitions()
    except Exception as exc:
        log.warning(f'Gateway Usage retention cleanup failed | Error:{exc!r}')
        return {
            'status': 'failed',
            'created_partitions': 0,
            'dropped_partitions': 0,
            'deleted_gateway_rows': 0,
            'deleted_method_rows': 0,
            'deleted_fine_gateway_rows': 0,
            'deleted_fine_method_rows': 0,
        }
    message = (
        f'Gateway Usage retention maintained | CreatedPartitions:{result.created_partitions} | '
        f'DroppedPartitions:{result.dropped_partitions} | DeletedGatewayRows:{result.deleted_gateway_rows} | '
        f'DeletedMethodRows:{result.deleted_method_rows} | DeletedFineGatewayRows:{result.deleted_fine_gateway_rows} | '
        f'DeletedFineMethodRows:{result.deleted_fine_method_rows}'
    )
    changed = (
        result.created_partitions
        or result.dropped_partitions
        or result.deleted_gateway_rows
        or result.deleted_method_rows
        or result.deleted_fine_gateway_rows
        or result.deleted_fine_method_rows
    )
    if changed:
        log.info(message)
    return {
        'status': 'ok',
        'created_partitions': result.created_partitions,
        'dropped_partitions': result.dropped_partitions,
        'deleted_gateway_rows': result.deleted_gateway_rows,
        'deleted_method_rows': result.deleted_method_rows,
        'deleted_fine_gateway_rows': result.deleted_fine_gateway_rows,
        'deleted_fine_method_rows': result.deleted_fine_method_rows,
    }
