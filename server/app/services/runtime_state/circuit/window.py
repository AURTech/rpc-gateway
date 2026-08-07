import asyncio
from dataclasses import dataclass
from datetime import datetime

from fastlog import log
from redis.asyncio import Redis

from app.infra import redis
from app.model.runtime_state.circuit import CircuitPolicy, CircuitWorkloadClass


@dataclass(frozen=True, slots=True, kw_only=True)
class CircuitWindowObservation:
    endpoint_id: str
    endpoint_version: int
    workload_class: CircuitWorkloadClass
    generation: int
    failed: bool
    observed_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CircuitWindow:
    samples: int
    failures: int

    @property
    def failure_rate(self) -> float:
        return self.failures / self.samples if self.samples else 0


type _BatchKey = tuple[str, int, CircuitWorkloadClass, int, int]


def _window_key(
    endpoint_id: str,
    endpoint_version: int,
    workload_class: CircuitWorkloadClass,
    generation: int,
    bucket_epoch: int,
) -> str:
    return redis.build_key(
        'runtime_state',
        'v3',
        'circuit_window',
        endpoint_id,
        str(endpoint_version),
        workload_class.value,
        str(generation),
        str(bucket_epoch),
    )


class CircuitWindowStore:
    def __init__(self, redis_client: Redis, policy: CircuitPolicy) -> None:
        self._redis = redis_client
        self._policy = policy

    def bucket_epoch(self, observed_at: datetime) -> int:
        epoch = int(observed_at.timestamp())
        size = self._policy.window_bucket_seconds
        return epoch - epoch % size

    async def record(self, batches: dict[_BatchKey, tuple[int, int]]) -> None:
        if not batches:
            return
        ttl = self._policy.window_seconds + self._policy.window_bucket_seconds * 2
        pipeline = self._redis.pipeline(transaction=False)
        for (endpoint_id, version, workload, generation, bucket), (samples, failures) in batches.items():
            key = _window_key(endpoint_id, version, workload, generation, bucket)
            pipeline.hincrby(key, 'samples', samples)
            pipeline.hincrby(key, 'failures', failures)
            pipeline.expire(key, ttl)
        await pipeline.execute()

    async def get(
        self,
        endpoint_id: str,
        endpoint_version: int,
        workload_class: CircuitWorkloadClass,
        generation: int,
    ) -> CircuitWindow:
        redis_time = await self._redis.time()
        now_epoch = int(redis_time[0])
        bucket_size = self._policy.window_bucket_seconds
        current = now_epoch - now_epoch % bucket_size
        count = self._policy.window_seconds // bucket_size
        keys = [
            _window_key(endpoint_id, endpoint_version, workload_class, generation, current - offset * bucket_size)
            for offset in range(count)
        ]
        values = await self._read_many(keys)
        samples = 0
        failures = 0
        for value in values:
            if not isinstance(value, list | tuple) or len(value) != 2:
                continue
            samples += _to_int(value[0])
            failures += _to_int(value[1])
        return CircuitWindow(samples=samples, failures=failures)

    async def _read_many(self, keys: list[str]) -> list[object]:
        pipeline = self._redis.pipeline(transaction=False)
        for key in keys:
            pipeline.hmget(key, ['samples', 'failures'])
        return list(await pipeline.execute())


class CircuitWindowDispatcher:
    def __init__(
        self,
        store: CircuitWindowStore,
        *,
        max_pending: int = 8192,
        coalesce_ms: int = 5,
    ) -> None:
        self._store = store
        self._queue: asyncio.Queue[CircuitWindowObservation] = asyncio.Queue(maxsize=max_pending)
        self._coalesce_seconds = coalesce_ms / 1000
        self._task: asyncio.Task[None] | None = None

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name='runtime-circuit-window')

    def submit(self, observation: CircuitWindowObservation) -> bool:
        if self._task is None or self._task.done():
            return False
        try:
            self._queue.put_nowait(observation)
        except asyncio.QueueFull:
            return False
        return True

    async def close(self, *, drain_seconds: float) -> None:
        task = self._task
        if task is None:
            return
        try:
            async with asyncio.timeout(drain_seconds):
                await self._queue.join()
        except TimeoutError:
            log.warning(f'Circuit window drain timed out | Pending:{self._queue.qsize()}')
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            if self._coalesce_seconds:
                await asyncio.sleep(self._coalesce_seconds)
            observations = [first]
            while not self._queue.empty():
                observations.append(self._queue.get_nowait())
            batches: dict[_BatchKey, list[int]] = {}
            for item in observations:
                key = (
                    item.endpoint_id,
                    item.endpoint_version,
                    item.workload_class,
                    item.generation,
                    self._store.bucket_epoch(item.observed_at),
                )
                values = batches.setdefault(key, [0, 0])
                values[0] += 1
                values[1] += int(item.failed)
            try:
                await self._store.record({key: (value[0], value[1]) for key, value in batches.items()})
            except Exception as exc:
                log.warning(f'Circuit window write failed | Observations:{len(observations)} | Error:{exc!r}')
            finally:
                for _item in observations:
                    self._queue.task_done()


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise RuntimeError('Circuit window counter is invalid.')
    if not isinstance(value, int | str | bytes | bytearray):
        raise RuntimeError('Circuit window counter is invalid.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('Circuit window counter is invalid.') from exc
    if parsed < 0:
        raise RuntimeError('Circuit window counter cannot be negative.')
    return parsed
