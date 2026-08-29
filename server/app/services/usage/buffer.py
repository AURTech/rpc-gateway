import asyncio
from dataclasses import dataclass
from typing import Final

from fastlog import log

from app.core.config import CONF
from app.infra import redis
from app.model.usage import GatewayUsageEvent
from app.services.base import Manager

USAGE_QUEUE_MAX_ITEMS = 8192
USAGE_BATCH_MAX_ITEMS = 256
USAGE_COALESCE_SECONDS = 0.005

APPEND_IF_CAPACITY_SCRIPT: Final[str] = """
if redis.call('XLEN', KEYS[1]) >= tonumber(ARGV[1]) then
    redis.call('INCR', KEYS[2])
    return false
end
return redis.call('XADD', KEYS[1], '*', 'payload', ARGV[2])
"""

APPEND_BATCH_IF_CAPACITY_SCRIPT: Final[str] = """
local capacity = tonumber(ARGV[1]) - redis.call('XLEN', KEYS[1])
local requested = #ARGV - 1
local accepted = math.max(0, math.min(capacity, requested))
for index = 1, accepted do
    redis.call('XADD', KEYS[1], '*', 'payload', ARGV[index + 1])
end
local dropped = requested - accepted
if dropped > 0 then
    redis.call('INCRBY', KEYS[2], dropped)
end
return accepted
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class BufferedUsageEvent:
    stream_id: str
    event: GatewayUsageEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayUsageBatch:
    events: list[BufferedUsageEvent]
    stream_ids: list[str]
    last_stream_id: str
    invalid: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GatewayUsageBacklog:
    entries: int
    oldest_age_seconds: float | None


class GatewayUsageBuffer(Manager):
    @staticmethod
    def stream_key() -> str:
        return redis.build_key('usage', 'v3', 'stream')

    @staticmethod
    def dropped_key() -> str:
        return redis.build_key('usage', 'v3', 'dropped')

    @staticmethod
    def flush_lease_key() -> str:
        return redis.build_key('usage', 'v3', 'flush')

    @staticmethod
    def retention_lease_key() -> str:
        return redis.build_key('usage', 'v3', 'retention')

    @staticmethod
    def rollup_lease_key() -> str:
        return redis.build_key('usage', 'v3', 'rollup')

    @classmethod
    async def append(cls, event: GatewayUsageEvent) -> None:
        # Reason: redis.asyncio eval is awaitable at runtime; stubs include a sync branch.
        stream_id = await cls.redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            APPEND_IF_CAPACITY_SCRIPT,
            2,
            cls.stream_key(),
            cls.dropped_key(),
            CONF.USAGE_STREAM_MAX_LENGTH,
            event.model_dump_json(exclude_defaults=True),
        )
        if not stream_id:
            raise BufferError('Gateway Usage Stream is full.')

    @classmethod
    async def append_many(cls, events: list[GatewayUsageEvent]) -> int:
        if not events:
            return 0
        payloads = [event.model_dump_json(exclude_defaults=True) for event in events]
        # Reason: redis.asyncio eval is awaitable at runtime; stubs include a sync branch.
        accepted = await cls.redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            APPEND_BATCH_IF_CAPACITY_SCRIPT,
            2,
            cls.stream_key(),
            cls.dropped_key(),
            CONF.USAGE_STREAM_MAX_LENGTH,
            *payloads,
        )
        return int(accepted or 0)

    @classmethod
    async def read_batch(cls, *, after_id: str, count: int) -> GatewayUsageBatch:
        rows = await cls.redis.xrange(cls.stream_key(), min=f'({after_id}', max='+', count=count)
        events: list[BufferedUsageEvent] = []
        stream_ids: list[str] = []
        invalid = 0
        for raw_stream_id, values in rows:
            stream_id = str(raw_stream_id)
            stream_ids.append(stream_id)
            raw = values.get('payload')
            if not isinstance(raw, str | bytes):
                invalid += 1
                log.warning(f'Gateway Usage event is invalid | StreamId:{stream_id} | Error:missing payload')
                continue
            try:
                event = GatewayUsageEvent.model_validate_json(raw)
            except ValueError as exc:
                invalid += 1
                log.warning(f'Gateway Usage event is invalid | StreamId:{stream_id} | Error:{exc!r}')
                continue
            events.append(BufferedUsageEvent(stream_id=stream_id, event=event))
        last_stream_id = stream_ids[-1] if stream_ids else after_id
        return GatewayUsageBatch(
            events=events,
            stream_ids=stream_ids,
            last_stream_id=last_stream_id,
            invalid=invalid,
        )

    @classmethod
    async def delete(cls, stream_ids: list[str]) -> int:
        if not stream_ids:
            return 0
        return int(await cls.redis.xdel(cls.stream_key(), *stream_ids))

    @classmethod
    async def delete_checkpointed(cls, *, checkpoint: str, count: int) -> int:
        if checkpoint == '0-0':
            return 0
        rows = await cls.redis.xrange(cls.stream_key(), min='-', max=checkpoint, count=count)
        stream_ids = [str(row[0]) for row in rows]
        return await cls.delete(stream_ids)

    @classmethod
    async def get_backlog(cls) -> GatewayUsageBacklog:
        entries = int(await cls.redis.xlen(cls.stream_key()))
        if entries == 0:
            return GatewayUsageBacklog(entries=0, oldest_age_seconds=None)
        rows = await cls.redis.xrange(cls.stream_key(), min='-', max='+', count=1)
        if not rows:
            return GatewayUsageBacklog(entries=entries, oldest_age_seconds=None)
        stream_id = str(rows[0][0])
        milliseconds_text, separator, _sequence = stream_id.partition('-')
        if not separator:
            raise ValueError('Gateway Usage Stream returned an invalid entry ID.')
        milliseconds = int(milliseconds_text)
        redis_seconds, redis_microseconds = await cls.redis.time()
        redis_milliseconds = int(redis_seconds) * 1000 + int(redis_microseconds) // 1000
        age_seconds = max(0.0, (redis_milliseconds - milliseconds) / 1000)
        return GatewayUsageBacklog(entries=entries, oldest_age_seconds=age_seconds)


class GatewayUsageRecorder:
    """Buffer usage events without allowing metering storage to delay Gateway responses."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[GatewayUsageEvent] = asyncio.Queue(maxsize=USAGE_QUEUE_MAX_ITEMS)
        self._writer: asyncio.Task[None] | None = None
        self._rejection_reason: str | None = None
        self._rejected_events = 0
        self._write_failed_events = 0
        self._stream_rejected_events = 0

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._writer is None:
            self._writer = asyncio.create_task(self._write_events(), name='gateway-usage-writer')

    def submit(self, event: GatewayUsageEvent) -> bool:
        if self._writer is None or self._writer.done():
            self._log_rejection('unavailable')
            return False
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._log_rejection('queue_full')
            return False
        self._log_resume()
        return True

    async def close(self, *, drain_seconds: float) -> None:
        if drain_seconds < 0:
            raise ValueError('Gateway Usage drain time cannot be negative.')
        writer = self._writer
        if writer is None:
            self._log_pending_losses()
            return
        if drain_seconds > 0:
            try:
                async with asyncio.timeout(drain_seconds):
                    await self._queue.join()
            except TimeoutError:
                log.warning(f'Gateway Usage writer drain timed out | Pending:{self.pending}')
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)
        self._writer = None
        self._discard_pending()
        self._log_pending_losses()

    async def _write_events(self) -> None:
        while True:
            first = await self._queue.get()
            if USAGE_COALESCE_SECONDS > 0:
                await asyncio.sleep(USAGE_COALESCE_SECONDS)
            batch = [first]
            while len(batch) < USAGE_BATCH_MAX_ITEMS:
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            try:
                await self._write_batch(batch)
            finally:
                for _item in batch:
                    self._queue.task_done()

    async def _write_batch(self, batch: list[GatewayUsageEvent]) -> None:
        try:
            written = await GatewayUsageBuffer.append_many(batch)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            first_failure = self._write_failed_events == 0
            self._write_failed_events += len(batch)
            if first_failure:
                log.warning(f'Gateway Usage batch write failed | Dropped:{len(batch)} | Error:{exc!r}')
            return
        if self._write_failed_events:
            log.warning(f'Gateway Usage batch writes resumed | Dropped:{self._write_failed_events}')
            self._write_failed_events = 0
        dropped = len(batch) - written
        if dropped:
            first_rejection = self._stream_rejected_events == 0
            self._stream_rejected_events += dropped
            if first_rejection:
                log.warning(f'Gateway Usage Stream rejected events | Dropped:{dropped}')
        elif self._stream_rejected_events:
            log.warning(f'Gateway Usage Stream writes resumed | Dropped:{self._stream_rejected_events}')
            self._stream_rejected_events = 0

    def _log_rejection(self, reason: str) -> None:
        self._rejected_events += 1
        if self._rejection_reason is not None:
            return
        self._rejection_reason = reason
        message = 'Gateway Usage recorder unavailable' if reason == 'unavailable' else 'Gateway Usage queue full'
        log.warning(message)

    def _log_resume(self) -> None:
        if self._rejection_reason is None:
            return
        log.warning(f'Gateway Usage recorder accepting events again | Dropped:{self._rejected_events}')
        self._rejection_reason = None
        self._rejected_events = 0

    def _log_pending_losses(self) -> None:
        if self._rejected_events:
            log.warning(f'Gateway Usage recorder stopped with rejected events | Dropped:{self._rejected_events}')
            self._rejection_reason = None
            self._rejected_events = 0
        if self._write_failed_events:
            log.warning(f'Gateway Usage recorder stopped after batch write failures | Dropped:{self._write_failed_events}')
            self._write_failed_events = 0
        if self._stream_rejected_events:
            log.warning(f'Gateway Usage recorder stopped after Stream rejections | Dropped:{self._stream_rejected_events}')
            self._stream_rejected_events = 0

    def _discard_pending(self) -> None:
        discarded = 0
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._queue.task_done()
            discarded += 1
        if discarded:
            log.warning(f'Gateway Usage events discarded during shutdown | Events:{discarded}')
