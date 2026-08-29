import asyncio
import time
from dataclasses import dataclass, field

from fastlog import log

from app.model.runtime_state.endpoint.health import EndpointHealth, HealthObservation
from app.services.runtime_state.endpoint.health.state import (
    HEALTH_WINDOW_SECONDS,
    HealthBatch,
    HealthBatchKey,
    HealthWriter,
    batch_key,
    make_batch,
    merge_batch,
)


@dataclass(slots=True, kw_only=True)
class _PendingHealth:
    batch: HealthBatch
    waiters: set[asyncio.Future[EndpointHealth]] = field(default_factory=set)


class HealthDispatcher:
    def __init__(
        self,
        *,
        max_batches: int,
        writer: HealthWriter,
        max_waiters: int = 2048,
        max_waiters_per_batch: int = 64,
        record_timeout_ms: int = 2000,
        coalesce_ms: int = 5,
    ) -> None:
        if max_batches < 1:
            raise ValueError('Health dispatcher batch limit must be positive.')
        if max_waiters < 1:
            raise ValueError('Health dispatcher waiter limit must be positive.')
        if max_waiters_per_batch < 1 or max_waiters_per_batch > max_waiters:
            raise ValueError('Health dispatcher per-batch waiter limit must be positive and not exceed the global limit.')
        if record_timeout_ms < 1:
            raise ValueError('Health dispatcher record timeout must be positive.')
        if coalesce_ms < 0:
            raise ValueError('Health dispatcher coalescing cadence cannot be negative.')
        self._max_waiters = max_waiters
        self._max_waiters_per_batch = max_waiters_per_batch
        self._record_timeout_seconds = record_timeout_ms / 1000
        self._coalesce_seconds = coalesce_ms / 1000
        self._writer = writer
        self._queue: asyncio.Queue[HealthBatchKey] = asyncio.Queue(maxsize=max_batches)
        self._pending: dict[HealthBatchKey, _PendingHealth] = {}
        self._active: dict[HealthBatchKey, _PendingHealth] = {}
        self._waiter_count = 0
        self._claimed_key: HealthBatchKey | None = None
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False

    @property
    def pending_batches(self) -> int:
        return len(self._pending) + len(self._active)

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._accepting = True
        self._worker = asyncio.create_task(self._write_batches(), name='runtime-health-dispatcher')

    def submit(self, observation: HealthObservation) -> bool:
        """Submit traffic evidence without waiting for Redis or blocking the request path."""
        return self._enqueue(observation, waiter=None) is not None

    async def record(self, observation: HealthObservation) -> EndpointHealth:
        """Submit control-plane evidence and wait until its aggregate batch has been recorded."""
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        pending = self._enqueue(observation, waiter=waiter)
        if pending is None:
            raise RuntimeError('Health dispatcher is unavailable or full.')
        try:
            async with asyncio.timeout(self._record_timeout_seconds):
                return await waiter
        except TimeoutError as exc:
            raise RuntimeError('Health observation record deadline exceeded.') from exc
        finally:
            if waiter in pending.waiters:
                pending.waiters.remove(waiter)
                self._waiter_count -= 1

    async def close(self, *, drain_seconds: float) -> None:
        """Stop admission and drain pending and active batches within the shutdown budget."""
        if drain_seconds < 0:
            raise ValueError('Health dispatcher drain time cannot be negative.')
        self._accepting = False
        worker = self._worker
        if worker is None:
            self._discard_pending()
            return
        if self.pending_batches > 0 and drain_seconds > 0:
            try:
                async with asyncio.timeout(drain_seconds):
                    await self._queue.join()
            except TimeoutError:
                log.warning(f'Health dispatcher drain timed out | Pending:{self.pending_batches}')
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        self._worker = None
        self._discard_pending()

    def _enqueue(
        self,
        observation: HealthObservation,
        *,
        waiter: asyncio.Future[EndpointHealth] | None,
    ) -> _PendingHealth | None:
        if not self._accepting or self._worker is None:
            return None
        key = batch_key(observation)
        pending = self._pending.get(key)
        if pending is not None:
            if waiter is not None and not self._add_waiter(pending, waiter):
                return None
            merge_batch(pending.batch, observation)
            return pending
        queue_full = self.pending_batches >= self._queue.maxsize or self._queue.full()
        if queue_full and not self._make_space(observation):
            return None
        pending = _PendingHealth(batch=make_batch(observation))
        if waiter is not None and not self._add_waiter(pending, waiter):
            return None
        self._pending[key] = pending
        self._queue.put_nowait(key)
        return pending

    def _add_waiter(self, pending: _PendingHealth, waiter: asyncio.Future[EndpointHealth]) -> bool:
        if self._waiter_count >= self._max_waiters or len(pending.waiters) >= self._max_waiters_per_batch:
            return False
        pending.waiters.add(waiter)
        self._waiter_count += 1
        return True

    async def _write_batches(self) -> None:
        while True:
            key = await self._queue.get()
            self._claimed_key = key
            if self._coalesce_seconds > 0:
                try:
                    await asyncio.sleep(self._coalesce_seconds)
                except asyncio.CancelledError:
                    self._claimed_key = None
                    self._queue.task_done()
                    raise
            self._claimed_key = None
            await self._write_queued(key)
            while True:
                try:
                    key = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await self._write_queued(key)

    async def _write_queued(self, key: HealthBatchKey) -> None:
        try:
            pending = self._pending.pop(key, None)
            if pending is None:
                return
            self._active[key] = pending
            try:
                await self._write_batch(pending)
            finally:
                self._active.pop(key, None)
        finally:
            self._queue.task_done()

    async def _write_batch(self, pending: _PendingHealth) -> None:
        if self._is_expired(pending.batch):
            self._fail_waiters(pending, RuntimeError('Health observation expired before it could be recorded.'))
            return
        try:
            health = await self._writer(pending.batch)
        except asyncio.CancelledError:
            self._fail_waiters(pending, RuntimeError('Health dispatcher closed before recording the batch.'))
            raise
        except TimeoutError:
            log.warning(f'Health observation batch write timed out | Samples:{pending.batch.samples}')
            self._fail_waiters(pending, RuntimeError('Health observation batch write timed out.'))
        except Exception as exc:
            log.warning(f'Health observation batch write failed | Samples:{pending.batch.samples} | Error:{exc!r}')
            self._fail_waiters(pending, RuntimeError('Health observation batch write failed.'))
        else:
            for waiter in pending.waiters:
                if not waiter.done():
                    waiter.set_result(health)
            self._clear_waiters(pending)

    def _fail_waiters(self, pending: _PendingHealth, error: RuntimeError) -> None:
        for waiter in pending.waiters:
            if not waiter.done():
                waiter.set_exception(error)
        self._clear_waiters(pending)

    def _clear_waiters(self, pending: _PendingHealth) -> None:
        self._waiter_count -= len(pending.waiters)
        pending.waiters.clear()

    def _make_space(self, observation: HealthObservation) -> bool:
        """Replace the oldest queued batch only when the added bucket is newer.

        Pending dict insertion order mirrors Queue FIFO order. The one key claimed by the worker
        remains pending during the coalescing sleep, so eviction skips it. Cancellation clears the
        claimed marker and accounts for its Queue item before shutdown discards pending batches.
        """
        oldest_key: HealthBatchKey | None = None
        oldest: _PendingHealth | None = None
        for key, pending in self._pending.items():
            if key != self._claimed_key:
                oldest_key = key
                oldest = pending
                break
        if oldest_key is None or oldest is None:
            return False
        added_epoch = batch_key(observation)[2]
        expired = self._is_expired(oldest.batch)
        if not expired and added_epoch <= oldest.batch.bucket_epoch:
            return False
        queued_key = self._queue.get_nowait()
        if queued_key != oldest_key:
            raise RuntimeError('Health dispatcher queue order is inconsistent.')
        self._queue.task_done()
        self._pending.pop(oldest_key)
        if expired:
            error = RuntimeError('Health observation expired before it could be recorded.')
        else:
            error = RuntimeError('Health observation was replaced by fresher traffic evidence.')
        self._fail_waiters(oldest, error)
        return True

    @staticmethod
    def _is_expired(batch: HealthBatch) -> bool:
        return batch.bucket_epoch + HEALTH_WINDOW_SECONDS <= int(time.time())

    def _discard_pending(self) -> None:
        error = RuntimeError('Health dispatcher closed before recording the batch.')
        for pending in self._pending.values():
            self._fail_waiters(pending, error)
        self._pending.clear()
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._queue.task_done()
