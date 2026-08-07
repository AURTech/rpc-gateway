from typing import TypedDict

from fastlog import log

from app.infra.db import in_tx
from app.infra.redis import acquire_redis_lease
from app.services.usage.buffer import GatewayUsageBuffer
from app.services.usage.store import GatewayUsageStore


class GatewayUsageRollupResult(TypedDict):
    lock_acquired: bool
    rolled_hours: int


class GatewayUsageRollupManager:
    @staticmethod
    async def rollup(*, limit: int, lease_seconds: int) -> GatewayUsageRollupResult:
        """Rebuild dirty hourly aggregates while holding the process-shared rollup lease."""
        lease = await acquire_redis_lease(
            GatewayUsageBuffer.redis,
            GatewayUsageBuffer.rollup_lease_key(),
            ttl_seconds=lease_seconds,
        )
        if lease is None:
            return {'lock_acquired': False, 'rolled_hours': 0}
        rolled_hours = 0
        try:
            for _index in range(limit):
                if not await lease.renew():
                    break
                async with in_tx() as connection:
                    hours = await GatewayUsageStore.get_rollup_hours(connection, limit=1)
                    if not hours:
                        break
                    bucket_hour = hours[0]
                    await GatewayUsageStore.rollup_hour(connection, bucket_hour)
                    rolled_hours += 1
            return {'lock_acquired': True, 'rolled_hours': rolled_hours}
        finally:
            try:
                await lease.release()
            except Exception as exc:
                log.warning(f'Gateway Usage rollup lease release failed | Error:{exc!r}')
