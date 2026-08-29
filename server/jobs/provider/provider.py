import asyncio
from datetime import datetime, timedelta

from app.clients.transport import HttpTransport
from app.core.errors import BadRequestError, ForbiddenError
from app.infra.db import in_tx
from app.infra.http_client import SharedHttpClient
from app.model.account import AccountStatus
from app.model.provider import ProviderSyncRunState, ProviderSyncStatus, ProviderSyncTrigger
from app.orm.provider import Provider, ProviderSyncRun, ProviderSyncRunItem
from app.services.endpoint import ManagedEndpointManager
from app.services.http_api_route import DatabaseEndpointRouteReferenceLookup
from app.services.provider import ProviderSyncManager
from app.services.provider.schedule import PROVIDER_SYNC_WINDOW_MINUTES, provider_sync_window_start
from app.util import datetime as datetime_util
from fastlog import log
from taskiq.abc.schedule_source import ScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

from jobs.registry import broker

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


async def _record_sync_failure(run: ProviderSyncRun, message: str) -> None:
    completed_at = datetime_util.now_utc()
    async with in_tx() as connection:
        await (
            ProviderSyncRun.filter(id=run.id, deleted_at=None)
            .using_db(connection)
            .update(
                state=ProviderSyncRunState.FAILED,
                completed_at=completed_at,
                error=message,
            )
        )
        await (
            Provider.filter(id=run.provider_id, deleted_at=None)
            .using_db(connection)
            .update(
                last_sync_at=completed_at,
                last_sync_status=ProviderSyncStatus.FAILED,
            )
        )


@broker.task(task_name='provider-sync-run')
async def run_provider_sync(run_id: str) -> dict[str, str]:
    run = await ProviderSyncRun.filter(id=run_id, deleted_at=None).first()
    if run is None:
        return {'state': 'missing'}
    updated = await ProviderSyncRun.filter(id=run.id, state=ProviderSyncRunState.QUEUED, deleted_at=None).update(
        state=ProviderSyncRunState.RUNNING,
        started_at=datetime_util.now_utc(),
    )
    if updated != 1:
        return {'state': str(run.state)}
    try:
        async with asyncio.timeout(PROVIDER_SYNC_TIMEOUT_SECONDS):
            result = await _manager().sync_provider(run.account_id, run.provider_id)
    except TimeoutError as exc:
        state = ProviderSyncRunState.FAILED
        await _record_sync_failure(run, 'Provider synchronization timed out.')
        log.warning(f'Provider sync run timed out | Provider:{run.provider_id} | Run:{run.id} | Error:{exc!r}')
    except Exception as exc:
        state = ProviderSyncRunState.FAILED
        await _record_sync_failure(run, 'Provider synchronization failed.')
        log.warning(f'Provider sync run failed | Provider:{run.provider_id} | Run:{run.id} | Error:{exc!r}')
    else:
        state = (
            ProviderSyncRunState.SUCCESS
            if result.status is ProviderSyncStatus.SUCCESS
            else ProviderSyncRunState.PARTIAL
            if result.status is ProviderSyncStatus.PARTIAL
            else ProviderSyncRunState.FAILED
        )
        run_error = (
            next((item.error for item in result.items if item.error), None) if state is ProviderSyncRunState.FAILED else None
        )
        try:
            async with in_tx() as connection:
                await (
                    ProviderSyncRun.filter(id=run.id, deleted_at=None)
                    .using_db(connection)
                    .update(
                        state=state,
                        completed_at=datetime_util.now_utc(),
                        created=result.created,
                        updated=result.updated,
                        restored=result.restored,
                        archived=result.archived,
                        skipped=result.skipped,
                        route_targets_added=result.route_targets_added,
                        route_targets_removed=result.route_targets_removed,
                        route_targets_skipped=result.route_targets_skipped,
                        error=run_error,
                    )
                )
                if result.items:
                    await ProviderSyncRunItem.bulk_create(
                        [
                            ProviderSyncRunItem(
                                run_id=run.id,
                                action=item.action,
                                chain=item.chain.value if item.chain is not None else None,
                                network=item.network.value if item.network is not None else None,
                                endpoint_id=item.endpoint_id,
                                external_id=item.external_id,
                                error=item.error,
                            )
                            for item in result.items
                        ],
                        using_db=connection,
                    )
        except Exception as exc:
            state = ProviderSyncRunState.FAILED
            await ProviderSyncRun.filter(id=run.id, deleted_at=None).update(
                state=state,
                completed_at=datetime_util.now_utc(),
                error='Provider synchronization result could not be recorded.',
            )
            log.warning(f'Provider sync result recording failed | Provider:{run.provider_id} | Run:{run.id} | Error:{exc!r}')
    stale_ids = (
        await ProviderSyncRun.filter(provider_id=run.provider_id, deleted_at=None)
        .order_by('-created_at')
        .offset(100)
        .values_list('id', flat=True)
    )
    if stale_ids:
        await ProviderSyncRun.filter(id__in=stale_ids).delete()
    return {'state': state.value}


async def reconcile_due_providers() -> dict[str, int]:
    started_at = datetime_util.now_utc()
    window_start = provider_sync_window_start(started_at)
    window_end = window_start + timedelta(minutes=PROVIDER_SYNC_WINDOW_MINUTES)
    advanced = await _advance_missed(window_start)
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
            run, created = await _create_scheduled_run(provider)
            if not created:
                skipped += 1
                continue
            outcome = await run_provider_sync(run.id)
            if outcome['state'] == ProviderSyncRunState.FAILED.value:
                failed += 1
            else:
                synced += 1
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


async def _create_scheduled_run(provider: Provider) -> tuple[ProviderSyncRun, bool]:
    active = (
        await ProviderSyncRun.filter(
            provider_id=provider.id,
            deleted_at=None,
            state__in=[ProviderSyncRunState.QUEUED, ProviderSyncRunState.RUNNING],
        )
        .order_by('-created_at')
        .first()
    )
    if active is not None:
        return active, False
    run = await ProviderSyncRun.create(
        provider_id=provider.id,
        account_id=provider.account_id,
        trigger=ProviderSyncTrigger.SCHEDULED,
        state=ProviderSyncRunState.QUEUED,
        queued_at=datetime_util.now_utc(),
    )
    return run, True


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
