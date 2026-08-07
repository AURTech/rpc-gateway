import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Final

from fastlog import log

from app.model.blockchain import Chain, Network
from app.model.runtime_state.endpoint.tip import TipObservation
from app.model.runtime_state.tip import Finality, TipUnit
from app.services.runtime_state.endpoint.tip.retry import RetryHeap
from app.services.runtime_state.endpoint.tip.write import TipWriteResult

TIP_RETRY_BASE_SECONDS: Final[float] = 0.25
TIP_RETRY_MAX_SECONDS: Final[float] = 5.0
TIP_RETRY_MIN_INTERVAL_SECONDS: Final[float] = 0.005
TIP_MAX_ITEMS: Final[int] = 1024
TIP_MAX_RETRY_ATTEMPTS: Final[int] = 10
TIP_MAX_RETRY_AGE_SECONDS: Final[float] = 30.0
TIP_RETRY_JITTER_MIN: Final[float] = 0.5
TIP_RETRY_JITTER_MAX: Final[float] = 1.0

type TipKey = tuple[str, Chain, Network, TipUnit, Finality]
type TipWriter = Callable[[TipObservation], Awaitable[TipWriteResult]]


def _tip_key(tip: TipObservation) -> TipKey:
    return tip.endpoint_id, tip.chain, tip.network, tip.unit, tip.finality


def _is_newer(tip: TipObservation, saved: TipObservation) -> bool:
    if tip.endpoint_version != saved.endpoint_version:
        return tip.endpoint_version > saved.endpoint_version
    return tip.observed_at > saved.observed_at


class TipDispatcher:
    """Coalesce observations with bounded admission, retry state, age, and task count."""

    def __init__(
        self,
        *,
        writer: TipWriter,
        max_items: int = TIP_MAX_ITEMS,
    ) -> None:
        if max_items < 1 or max_items > TIP_MAX_ITEMS:
            raise ValueError(f'Tip dispatcher item limit must be between 1 and {TIP_MAX_ITEMS}.')
        self._max_items = max_items
        self._writer = writer
        self._queue: asyncio.Queue[TipKey] = asyncio.Queue(maxsize=max_items)
        self._queued: set[TipKey] = set()
        self._pending: dict[TipKey, TipObservation] = {}
        self._watermarks: dict[TipKey, TipObservation] = {}
        self._retry_attempts: dict[TipKey, int] = {}
        self._admitted_at: dict[TipKey, float] = {}
        self._retries: RetryHeap[TipKey] = RetryHeap(max_items)
        self._retry_wake = asyncio.Event()
        self._drained = asyncio.Event()
        self._drained.set()
        self._writer_task: asyncio.Task[None] | None = None
        self._retry_task: asyncio.Task[None] | None = None
        self._active_key: TipKey | None = None
        self._accepting = False

    @property
    def pending_items(self) -> int:
        return len(self._pending)

    async def start(self) -> None:
        if self._writer_task is not None:
            return
        self._accepting = True
        self._writer_task = asyncio.create_task(self._write_tips(), name='runtime-tip-writer')
        self._retry_task = asyncio.create_task(self._coordinate_retries(), name='runtime-tip-retry')

    def submit(self, tip: TipObservation) -> bool:
        if not self._accepting or self._writer_task is None:
            return False
        key = _tip_key(tip)
        watermark = self._watermarks.get(key)
        if watermark is not None and not _is_newer(tip, watermark):
            return False
        if watermark is None and len(self._watermarks) >= self._max_items:
            return False

        if watermark is None:
            self._admitted_at[key] = asyncio.get_running_loop().time()
        self._watermarks[key] = tip
        self._pending[key] = tip
        self._drained.clear()
        if key == self._active_key or key in self._queued or key in self._retries:
            return True
        return self._enqueue(key)

    async def close(self, *, drain_seconds: float) -> None:
        """Stop admission and drain queued observations within the caller's shutdown budget."""
        if drain_seconds < 0:
            raise ValueError('Tip dispatcher drain time cannot be negative.')
        self._accepting = False
        writer_task = self._writer_task
        retry_task = self._retry_task
        if writer_task is None:
            self._discard_pending()
            return

        if drain_seconds > 0:
            try:
                async with asyncio.timeout(drain_seconds):
                    await self._drained.wait()
            except TimeoutError:
                log.warning(f'Tip dispatcher drain timed out | Pending:{self.pending_items}')

        writer_task.cancel()
        if retry_task is not None:
            retry_task.cancel()
        try:
            tasks = [writer_task]
            if retry_task is not None:
                tasks.append(retry_task)
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._writer_task = None
            self._retry_task = None
            self._discard_pending()

    async def _write_tips(self) -> None:
        while True:
            key = await self._queue.get()
            self._queued.discard(key)
            tip = self._pending.get(key)
            if tip is None:
                self._queue.task_done()
                continue
            now = asyncio.get_running_loop().time()
            if self._retry_age_exhausted(key, now=now):
                self._forget(key)
                self._queue.task_done()
                continue

            self._active_key = key
            completed = False
            try:
                completed = await self._write_tip(tip)
            finally:
                self._active_key = None
                current = self._pending.get(key)
                if completed:
                    self._retry_attempts.pop(key, None)
                    if current == tip:
                        self._forget(key)
                    elif current is not None:
                        self._admitted_at[key] = asyncio.get_running_loop().time()
                        self._enqueue(key)
                elif current is not None:
                    self._schedule_retry(key)
                else:
                    self._forget(key)
                self._queue.task_done()

    async def _write_tip(self, tip: TipObservation) -> bool:
        try:
            result = await self._writer(tip)
            if result in (TipWriteResult.STORED, TipWriteResult.STALE_NOOP):
                return True
            if result in (TipWriteResult.CAPACITY_REJECTED, TipWriteResult.FUTURE_REJECTED):
                return False
            raise RuntimeError('Tip writer returned an invalid result.')
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            log.warning('Tip observation write timed out')
        except Exception as exc:
            log.warning(f'Tip observation write failed | Error:{exc!r}')
        return False

    def _schedule_retry(self, key: TipKey) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        admitted_at = self._admitted_at.get(key, now)
        age = now - admitted_at
        attempt = self._retry_attempts.get(key, 0) + 1
        if attempt > TIP_MAX_RETRY_ATTEMPTS or age >= TIP_MAX_RETRY_AGE_SECONDS:
            self._forget(key)
            return

        self._retry_attempts[key] = attempt
        exponent = min(attempt - 1, 6)
        backoff = min(TIP_RETRY_BASE_SECONDS * 2**exponent, TIP_RETRY_MAX_SECONDS)
        delay = backoff * random.uniform(TIP_RETRY_JITTER_MIN, TIP_RETRY_JITTER_MAX)
        remaining = TIP_MAX_RETRY_AGE_SECONDS - age
        deadline = now + min(delay, remaining)
        if self._retries.put(key, deadline):
            self._retry_wake.set()

    async def _coordinate_retries(self) -> None:
        next_retry_at = 0.0
        while True:
            deadline = self._retries.next_deadline()
            if deadline is None:
                self._retry_wake.clear()
                if self._retries:
                    continue
                await self._retry_wake.wait()
                continue

            deadline = max(deadline, next_retry_at)
            delay = deadline - asyncio.get_running_loop().time()
            if delay > 0:
                self._retry_wake.clear()
                try:
                    async with asyncio.timeout(delay):
                        await self._retry_wake.wait()
                    continue
                except TimeoutError:
                    pass

            key = self._retries.pop()
            if key is not None and key in self._pending:
                now = asyncio.get_running_loop().time()
                if self._retry_age_exhausted(key, now=now):
                    self._forget(key)
                    continue
                self._enqueue(key)
                next_retry_at = now + TIP_RETRY_MIN_INTERVAL_SECONDS

    def _enqueue(self, key: TipKey) -> bool:
        if key in self._queued or key == self._active_key:
            return True
        try:
            self._queue.put_nowait(key)
        except asyncio.QueueFull:
            return False
        self._queued.add(key)
        return True

    def _forget(self, key: TipKey) -> None:
        self._pending.pop(key, None)
        self._watermarks.pop(key, None)
        self._retry_attempts.pop(key, None)
        self._admitted_at.pop(key, None)
        if not self._pending:
            self._drained.set()

    def _retry_age_exhausted(self, key: TipKey, *, now: float) -> bool:
        admitted_at = self._admitted_at.get(key)
        return admitted_at is not None and now - admitted_at >= TIP_MAX_RETRY_AGE_SECONDS

    def _discard_pending(self) -> None:
        self._pending.clear()
        self._watermarks.clear()
        self._retry_attempts.clear()
        self._admitted_at.clear()
        self._retries.clear()
        self._queued.clear()
        self._retry_wake.clear()
        self._active_key = None
        self._drained.set()
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._queue.task_done()
