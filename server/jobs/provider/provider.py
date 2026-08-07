import asyncio
from datetime import datetime, timedelta

from app.clients.transport import HttpTransport
from app.core.errors import BadRequestError, ForbiddenError
from app.infra.db import in_tx
from app.infra.http_client import SharedHttpClient
from app.model.account import AccountStatus
from app.model.provider import ProviderSyncStatus
from app.orm.provider import Provider
from app.services.endpoint import ManagedEndpointManager
from app.services.http_api_route import DatabaseEndpointRouteReferenceLookup
from app.services.provider import ProviderSyncManager
from app.services.provider.schedule import PROVIDER_SYNC_WINDOW_MINUTES, provider_sync_window_start
from app.util import datetime as datetime_util
from fastlog import log
from taskiq.abc.schedule_source import ScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

PROVIDER_RECONCILE_SCHEDULE = 'provider-daily-reconcile'
PROVIDER_RECONCILE_SCHEDULE_ID = 'provider-daily-reconcile'
PROVIDER_SYNC_TIMEOUT_SECONDS = 300
PROVIDER_SYNC_TICK_SECONDS = PROVIDER_SYNC_WINDOW_MINUTES * 60

ADVANCE_MISSED_SQL = """
UPDATE provider
SET next_sync_at = next_sync_at
    + CEIL(EXTRACT(EPOCH FROM ($1::timestamptz - next_sync_at)) / 86400)::integer * INTERVAL '1 day'
WHERE deleted_at IS NULL
  AND enabled = TRUE
  AND sync_enabled = TRUE
  AND next_sync_at < $1::timestamptz
"""


class ProviderScheduleSource(ScheduleSource):
    async def get_schedules(self) -> list[ScheduledTask]:
        return [
            ScheduledTask(
                task_name=PROVIDER_RECONCILE_SCHEDULE,
                schedule_id=PROVIDER_RECONCILE_SCHEDULE_ID,
                labels={},
                args=[],
                kwargs={},
                interval=PROVIDER_SYNC_TICK_SECONDS,
            )
        ]


def _manager() -> ProviderSyncManager:
    route_references = DatabaseEndpointRouteReferenceLookup()
    return ProviderSyncManager(HttpTransport(SharedHttpClient.get()), ManagedEndpointManager(route_references))


async def reconcile_due_providers() -> dict[str, int]:
    started_at = datetime_util.now_utc()
    window_start = provider_sync_window_start(started_at)
    window_end = window_start + timedelta(minutes=PROVIDER_SYNC_WINDOW_MINUTES)
    advanced = await _advance_missed(window_start)
    manager = _manager()
    checked = 0
    synced = 0
    skipped = 0
    failed = 0
    while True:
        provider = await _next_provider(window_start, window_end)
        if provider is None:
            break
        if not await _advance_provider(provider):
            continue
        checked += 1
        try:
            async with asyncio.timeout(PROVIDER_SYNC_TIMEOUT_SECONDS):
                result = await manager.sync_provider(provider.account_id, provider.id)
            if result.status is ProviderSyncStatus.FAILED:
                failed += 1
            else:
                synced += 1
        except TimeoutError:
            failed += 1
            await _record_timeout(provider)
            log.warning(f'Provider automatic sync timed out | Provider:{provider.id}')
        except (BadRequestError, ForbiddenError):
            skipped += 1
        except Exception as exc:
            failed += 1
            log.warning(f'Provider automatic sync failed | Provider:{provider.id} | Error:{exc!r}')
    log.info(
        f'Provider automatic sync finished | Advanced:{advanced} | Checked:{checked} | Synced:{synced} | '
        f'Skipped:{skipped} | Failed:{failed}'
    )
    return {'advanced': advanced, 'checked': checked, 'synced': synced, 'skipped': skipped, 'failed': failed}


async def _advance_missed(window_start: datetime) -> int:
    async with in_tx() as connection:
        advanced, _ = await connection.execute_query(ADVANCE_MISSED_SQL, [window_start])
    return advanced


async def _next_provider(window_start: datetime, window_end: datetime) -> Provider | None:
    return await (
        Provider.filter(
            deleted_at=None,
            enabled=True,
            sync_enabled=True,
            next_sync_at__gte=window_start,
            next_sync_at__lt=window_end,
            account__deleted_at=None,
            account__status=AccountStatus.ACTIVE,
        )
        .order_by('next_sync_at', 'account_id', 'id')
        .first()
    )


async def _advance_provider(provider: Provider) -> bool:
    scheduled_at = provider.next_sync_at
    if scheduled_at is None:
        return False
    next_sync_at = scheduled_at + timedelta(days=1)
    updated = await Provider.filter(
        id=provider.id,
        deleted_at=None,
        enabled=True,
        sync_enabled=True,
        next_sync_at=scheduled_at,
    ).update(next_sync_at=next_sync_at)
    return updated == 1


async def _record_timeout(provider: Provider) -> None:
    await Provider.filter(id=provider.id, deleted_at=None, last_sync_at=provider.last_sync_at).update(
        last_sync_at=datetime_util.now_utc(),
        last_sync_status=ProviderSyncStatus.FAILED,
        last_sync_error='Provider automatic sync timed out.',
        last_sync_created=0,
        last_sync_updated=0,
        last_sync_restored=0,
        last_sync_archived=0,
        last_sync_skipped=1,
    )
