import asyncio

from fastlog import log

from app.model.system_cache import CacheEntry, CacheFlightLease, CacheKey
from app.services.system_cache.interface import CacheStore, DistributedFlight

PUBLISH_MAX_ITEMS = 64
PUBLISH_MAX_BYTES = 256 * 1024 * 1024
PUBLISH_WORKERS = 2
PUBLISH_TIMEOUT_SECONDS = 5.0
FLIGHT_RELEASE_MAX_ITEMS = 1024
FLIGHT_RELEASE_WORKERS = 8
FLIGHT_RELEASE_TIMEOUT_SECONDS = 1.0


class PostgresRetentionPublisher:
    """Publish fenced PostgreSQL retention entries without retaining request latency or unbounded memory."""

    def __init__(self, store: CacheStore) -> None:
        self._store = store
        self._slots = asyncio.Semaphore(PUBLISH_WORKERS)
        self._tasks: set[asyncio.Task[None]] = set()
        self._pending_bytes = 0
        self._rejection_logged = False
        self._failure_logged = False

    @property
    def pending_items(self) -> int:
        return len(self._tasks)

    @property
    def pending_bytes(self) -> int:
        return self._pending_bytes

    def submit(
        self,
        entry: CacheEntry,
        lease: CacheFlightLease,
        *,
        refresh: bool,
        flight: DistributedFlight,
        heartbeat: asyncio.Task[None],
        ownership_lost: asyncio.Event,
    ) -> bool:
        payload_bytes = len(entry.payload)
        if len(self._tasks) >= PUBLISH_MAX_ITEMS or self._pending_bytes + payload_bytes > PUBLISH_MAX_BYTES:
            if not self._rejection_logged:
                log.warning(
                    f'System Cache PostgreSQL retention publish rejected | PendingItems:{self.pending_items}'
                    f' | PendingBytes:{self.pending_bytes}'
                )
                self._rejection_logged = True
            return False
        self._rejection_logged = False
        self._pending_bytes += payload_bytes
        task = asyncio.create_task(
            self._publish(
                entry,
                lease,
                refresh=refresh,
                flight=flight,
                heartbeat=heartbeat,
                ownership_lost=ownership_lost,
            ),
            name='system-cache-postgres-retention-publisher',
        )
        self._tasks.add(task)
        task.add_done_callback(self._finish)
        return True

    async def close(self, *, drain_seconds: float) -> None:
        if drain_seconds < 0:
            raise ValueError('PostgreSQL retention publisher drain time cannot be negative.')
        tasks = tuple(self._tasks)
        if tasks and drain_seconds > 0:
            try:
                async with asyncio.timeout(drain_seconds):
                    await asyncio.gather(*tasks, return_exceptions=True)
            except TimeoutError:
                log.warning(f'System Cache PostgreSQL retention publisher drain timed out | Pending:{self.pending_items}')
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _publish(
        self,
        entry: CacheEntry,
        lease: CacheFlightLease,
        *,
        refresh: bool,
        flight: DistributedFlight,
        heartbeat: asyncio.Task[None],
        ownership_lost: asyncio.Event,
    ) -> None:
        publish_succeeded = False
        release_succeeded = False
        try:
            async with self._slots:
                if ownership_lost.is_set():
                    return
                try:
                    async with asyncio.timeout(PUBLISH_TIMEOUT_SECONDS):
                        applied = await self._store.commit(entry, lease, refresh=refresh)
                except TimeoutError as exc:
                    self._log_failure('PostgreSQL retention publish timed out', exc)
                    return
                except Exception as exc:
                    self._log_failure('PostgreSQL retention publish failed', exc)
                    return
                if applied:
                    publish_succeeded = True
                else:
                    self._log_failure('PostgreSQL retention fenced write rejected', None)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            try:
                async with asyncio.timeout(FLIGHT_RELEASE_TIMEOUT_SECONDS):
                    await flight.release(entry.key, lease)
            except Exception as exc:
                self._log_failure('PostgreSQL retention flight release failed', exc)
            else:
                release_succeeded = True
            self._pending_bytes -= len(entry.payload)
            if publish_succeeded and release_succeeded:
                self._failure_logged = False

    def _finish(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._log_failure('PostgreSQL retention publisher task failed', error)

    def _log_failure(self, message: str, error: BaseException | None) -> None:
        if self._failure_logged:
            return
        self._failure_logged = True
        log.warning(f'System Cache {message} | Error:{error!r}')


class FlightReleaser:
    """Release tracked cache leases outside request tasks with bounded concurrency."""

    def __init__(self) -> None:
        self._slots = asyncio.Semaphore(FLIGHT_RELEASE_WORKERS)
        self._tasks: set[asyncio.Task[None]] = set()
        self._heartbeats: dict[asyncio.Task[None], asyncio.Task[None]] = {}
        self._rejection_logged = False
        self._failure_logged = False

    @property
    def pending(self) -> int:
        return len(self._tasks)

    def submit(
        self,
        *,
        flight: DistributedFlight,
        key: CacheKey,
        lease: CacheFlightLease,
        heartbeat: asyncio.Task[None],
    ) -> bool:
        if len(self._tasks) >= FLIGHT_RELEASE_MAX_ITEMS:
            if not self._rejection_logged:
                log.warning(f'System Cache flight release rejected | Pending:{self.pending}')
                self._rejection_logged = True
            return False
        self._rejection_logged = False
        task = asyncio.create_task(
            self._release(flight=flight, key=key, lease=lease, heartbeat=heartbeat),
            name='system-cache-flight-release',
        )
        self._tasks.add(task)
        self._heartbeats[task] = heartbeat
        task.add_done_callback(self._finish)
        return True

    async def close(self, *, drain_seconds: float) -> None:
        if drain_seconds < 0:
            raise ValueError('Cache flight release drain time cannot be negative.')
        tasks = tuple(self._tasks)
        if tasks and drain_seconds > 0:
            try:
                async with asyncio.timeout(drain_seconds):
                    await asyncio.gather(*tasks, return_exceptions=True)
            except TimeoutError:
                log.warning(f'System Cache flight release drain timed out | Pending:{self.pending}')
        tasks = tuple(self._tasks)
        heartbeats = tuple(self._heartbeats.values())
        for heartbeat in heartbeats:
            heartbeat.cancel()
        for task in tasks:
            task.cancel()
        if tasks or heartbeats:
            await asyncio.gather(*tasks, *heartbeats, return_exceptions=True)

    async def _release(
        self,
        *,
        flight: DistributedFlight,
        key: CacheKey,
        lease: CacheFlightLease,
        heartbeat: asyncio.Task[None],
    ) -> None:
        try:
            async with self._slots:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                try:
                    async with asyncio.timeout(FLIGHT_RELEASE_TIMEOUT_SECONDS):
                        await flight.release(key, lease)
                except TimeoutError as exc:
                    self._log_failure('timed out', exc)
                except Exception as exc:
                    self._log_failure('failed', exc)
                else:
                    self._failure_logged = False
        finally:
            heartbeat.cancel()

    def _finish(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        heartbeat = self._heartbeats.pop(task, None)
        if heartbeat is not None:
            heartbeat.cancel()
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                self._log_failure('task failed', error)

    def _log_failure(self, message: str, error: BaseException) -> None:
        if self._failure_logged:
            return
        self._failure_logged = True
        log.warning(f'System Cache flight release {message} | Error:{error!r}')
