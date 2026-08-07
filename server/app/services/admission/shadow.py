import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastlog import log

from app.model.admission import AdmissionRuntimePolicy
from app.services.admission.store import TokenBucketRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class ShadowAdmission:
    policy: AdmissionRuntimePolicy
    buckets: tuple[TokenBucketRequest, ...]


class ShadowAdmissionDispatcher:
    def __init__(
        self,
        *,
        namespace: str,
        max_pending: int,
        workers: int,
        writer: Callable[[ShadowAdmission], Awaitable[None]],
    ) -> None:
        if not 1 <= max_pending <= 65_536:
            raise ValueError('Shadow admission queue limit must be between 1 and 65536.')
        if not 1 <= workers <= 256:
            raise ValueError('Shadow admission worker count must be between 1 and 256.')
        self._queue: asyncio.Queue[ShadowAdmission] = asyncio.Queue(maxsize=max_pending)
        self._namespace = namespace
        self._worker_count = workers
        self._writer = writer
        self._tasks: tuple[asyncio.Task[None], ...] = ()
        self._active = 0
        self._accepting = False

    @property
    def pending(self) -> int:
        return self._queue.qsize() + self._active

    async def start(self) -> None:
        if self._tasks:
            return
        self._accepting = True
        self._tasks = tuple(
            asyncio.create_task(self._write_admissions(), name=f'admission-{self._namespace}-shadow-{index}')
            for index in range(self._worker_count)
        )

    def submit(self, admission: ShadowAdmission) -> bool:
        """Queue one observation without yielding or applying backpressure to the request."""
        if not self._accepting or not self._tasks:
            return False
        try:
            self._queue.put_nowait(admission)
        except asyncio.QueueFull:
            return False
        return True

    async def close(self, *, drain_seconds: float) -> None:
        """Stop admission and drain queued observations within a bounded shutdown budget."""
        if drain_seconds < 0:
            raise ValueError('Shadow admission drain time cannot be negative.')
        self._accepting = False
        tasks = self._tasks
        if not tasks:
            self._discard_pending()
            return
        if self.pending > 0 and drain_seconds > 0:
            try:
                async with asyncio.timeout(drain_seconds):
                    await self._queue.join()
            except TimeoutError:
                log.warning(f'Admission shadow drain timed out | Namespace:{self._namespace} | Pending:{self.pending}')
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks = ()
        self._discard_pending()

    async def _write_admissions(self) -> None:
        while True:
            admission = await self._queue.get()
            self._active += 1
            try:
                await self._writer(admission)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(f'Admission shadow write failed | Namespace:{self._namespace} | Error:{exc!r}')
            finally:
                self._active -= 1
                self._queue.task_done()

    def _discard_pending(self) -> None:
        discarded = 0
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            discarded += 1
            self._queue.task_done()
        if discarded:
            log.warning(f'Admission shadow discarded observations | Namespace:{self._namespace} | Count:{discarded}')
