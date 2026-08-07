import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastlog import log
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import UnavailableError
from app.model.runtime_state.circuit import (
    CircuitDecision,
    CircuitObservation,
    CircuitOpenReason,
    CircuitOutcome,
    CircuitPolicy,
    CircuitSnapshot,
    CircuitState,
    CircuitWorkloadClass,
)
from app.services.runtime_state.circuit.state import (
    CircuitRecord,
    apply_outcome,
    grant_probe,
    make_decision,
    make_open,
    next_backoff_step,
    to_snapshot,
)
from app.services.runtime_state.circuit.store import CircuitRaw, CircuitStore, make_key
from app.services.runtime_state.circuit.window import (
    CircuitWindowDispatcher,
    CircuitWindowObservation,
    CircuitWindowStore,
)

type CircuitKey = tuple[str, int] | tuple[str, int, CircuitWorkloadClass]

CIRCUIT_RESULT_QUEUE_MAX_ITEMS = 8192


@dataclass(frozen=True, slots=True, kw_only=True)
class _CachedState:
    decision: CircuitDecision | None
    decision_expires_at: float
    record: CircuitRecord
    raw: CircuitRaw
    redis_now: datetime | None
    clock_anchor: float | None
    expires_at: float


@dataclass(frozen=True, slots=True, kw_only=True)
class _StateResult:
    record: CircuitRecord
    raw: CircuitRaw
    redis_now: datetime | None
    clock_anchor: float | None
    applied: bool


@dataclass(slots=True, kw_only=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class _QueuedObservation:
    decision: CircuitDecision
    observation: CircuitObservation


class CircuitManager:
    """Coordinate shared Circuit state with bounded-stale healthy admission.

    Closed state with zero failures can be reused for ``cache_ttl_ms`` in each process. A healthy
    result admitted from that cache does not read Redis, so failures recorded by another process
    can remain unseen until the local cache expires. Failure results invalidate the local entry
    before their shared write, while Half-open results always retain shared token and epoch checks.
    """

    def __init__(self, redis_client: Redis, policy: CircuitPolicy | None = None) -> None:
        self._policy = policy or CircuitPolicy()
        self._store = CircuitStore(redis_client, state_ttl_seconds=self._policy.state_ttl_seconds)
        self._window_store = CircuitWindowStore(redis_client, self._policy)
        self._window_dispatcher = CircuitWindowDispatcher(self._window_store)
        self._cache: dict[CircuitKey, _CachedState] = {}
        self._locks: dict[CircuitKey, _LockEntry] = {}
        self._result_queue: asyncio.Queue[_QueuedObservation] = asyncio.Queue(maxsize=CIRCUIT_RESULT_QUEUE_MAX_ITEMS)
        self._pending_results: dict[CircuitKey, int] = {}
        self._result_writer: asyncio.Task[None] | None = None
        self._accepting_results = False
        self._result_rejection_reason: str | None = None
        self._result_failure_logged = False

    async def start(self) -> None:
        await self._window_dispatcher.start()
        if self._result_writer is None:
            self._accepting_results = True
            self._start_result_writer()

    @property
    def pending_window_observations(self) -> int:
        return self._window_dispatcher.pending

    @property
    def pending_result_observations(self) -> int:
        return self._result_queue.qsize()

    async def drain_results(self, *, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError('Circuit result drain timeout must be positive.')
        async with asyncio.timeout(timeout_seconds):
            await self._result_queue.join()

    async def close(self, *, drain_seconds: float) -> None:
        if drain_seconds < 0:
            raise ValueError('Circuit result drain time cannot be negative.')
        deadline = time.monotonic() + drain_seconds
        self._accepting_results = False
        writer = self._result_writer
        if writer is not None:
            if drain_seconds > 0:
                try:
                    async with asyncio.timeout(drain_seconds):
                        await self._result_queue.join()
                except TimeoutError:
                    log.warning(f'Circuit result writer drain timed out | Pending:{self.pending_result_observations}')
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)
            self._result_writer = None
        self._discard_results()
        remaining = max(0.0, deadline - time.monotonic())
        await self._window_dispatcher.close(drain_seconds=remaining)

    async def get(
        self,
        endpoint_id: str,
        endpoint_version: int,
        workload_class: CircuitWorkloadClass = CircuitWorkloadClass.STANDARD,
    ) -> CircuitSnapshot:
        """Read shared Circuit state; Redis failures are surfaced as system errors."""
        key = make_key(endpoint_id, endpoint_version, workload_class)
        try:
            async with asyncio.timeout(self._policy.operation_timeout_ms / 1000):
                stored = await self._store.read(
                    key,
                    endpoint_id=endpoint_id,
                    endpoint_version=endpoint_version,
                    workload_class=workload_class,
                )
                return to_snapshot(stored.record)
        except (TimeoutError, RedisError, RuntimeError, ValueError) as exc:
            log.error(f'Circuit state read failed | Endpoint:{endpoint_id} | Version:{endpoint_version} | Error:{exc!r}')
            raise UnavailableError('Circuit state is unavailable.') from exc

    async def before_attempt(self, endpoint_id: str, endpoint_version: int) -> CircuitDecision:
        return await self.before_scoped_attempt(endpoint_id, endpoint_version, CircuitWorkloadClass.STANDARD)

    async def before_scoped_attempt(
        self,
        endpoint_id: str,
        endpoint_version: int,
        workload_class: CircuitWorkloadClass,
    ) -> CircuitDecision:
        """Return one bounded-stale admission decision and reserve a Half-open probe when eligible.

        Raises:
            UnavailableError: shared Circuit state cannot be read or transitioned.

        Side effects:
            May atomically write a Half-open probe reservation or an expired-probe Open transition to Redis.
        """
        key = make_key(endpoint_id, endpoint_version, workload_class)
        cache_key = (endpoint_id, endpoint_version, workload_class)
        cached = self._get_cached_decision(cache_key)
        if cached is not None:
            return cached
        try:
            async with self._hold_lock(cache_key):
                cached = self._get_cached_decision(cache_key)
                if cached is not None:
                    return cached
                async with asyncio.timeout(self._policy.operation_timeout_ms / 1000):
                    result = await self._admit_shared(
                        key=key,
                        endpoint_id=endpoint_id,
                        endpoint_version=endpoint_version,
                        workload_class=workload_class,
                    )
                    token = result.record.probe_token if result.applied else None
                    decision = make_decision(result.record, allowed=result.applied, probe_token=token)
                    self._cache_record(cache_key, result=result, decision=decision)
                    return decision
        except (TimeoutError, RedisError, RuntimeError, ValueError) as exc:
            log.error(f'Circuit admission failed | Endpoint:{endpoint_id} | Version:{endpoint_version} | Error:{exc!r}')
            raise UnavailableError('Circuit state is unavailable.') from exc

    def submit(self, decision: CircuitDecision, observation: CircuitObservation) -> bool:
        """Submit an Endpoint result without allowing Redis writes to delay the request path."""
        if not decision.allowed:
            return False
        outcome = observation.outcome
        if decision.state is CircuitState.CLOSED and outcome in {
            CircuitOutcome.SUCCESS,
            CircuitOutcome.HARD_FAILURE,
            CircuitOutcome.SAMPLED_FAILURE,
        }:
            self._window_dispatcher.submit(
                CircuitWindowObservation(
                    endpoint_id=decision.endpoint_id,
                    endpoint_version=decision.endpoint_version,
                    workload_class=decision.workload_class,
                    generation=decision.window_generation,
                    failed=outcome is not CircuitOutcome.SUCCESS,
                    observed_at=datetime.now(UTC),
                )
            )
        if outcome is CircuitOutcome.IGNORED and decision.state is CircuitState.CLOSED:
            return True
        if outcome is CircuitOutcome.SAMPLED_FAILURE and decision.state is CircuitState.CLOSED:
            return True
        cache_key = (decision.endpoint_id, decision.endpoint_version, decision.workload_class)
        cached = self._get_cached_state(cache_key)
        if cached is not None and (cached.record.state is not decision.state or cached.record.epoch != decision.epoch):
            return False
        if outcome in {CircuitOutcome.HARD_FAILURE, CircuitOutcome.SAMPLED_FAILURE, CircuitOutcome.THROTTLED}:
            self._cache.pop(cache_key, None)
        closed_success = decision.state is CircuitState.CLOSED and outcome is CircuitOutcome.SUCCESS
        if (
            closed_success
            and decision.failures == 0
            and cached is not None
            and cached.record.failures == 0
            and self._pending_results.get(cache_key, 0) == 0
        ):
            return True
        if not self._accepting_results or self._result_writer is None or self._result_writer.done():
            self._log_result_rejection('unavailable')
            return False
        try:
            self._result_queue.put_nowait(_QueuedObservation(decision=decision, observation=observation))
        except asyncio.QueueFull:
            self._log_result_rejection('queue_full')
            return False
        self._pending_results[cache_key] = self._pending_results.get(cache_key, 0) + 1
        self._result_rejection_reason = None
        return True

    def _start_result_writer(self) -> None:
        task = asyncio.create_task(self._write_results(), name='runtime-circuit-results')
        self._result_writer = task
        task.add_done_callback(self._result_writer_done)

    def _result_writer_done(self, task: asyncio.Task[None]) -> None:
        if self._result_writer is task:
            self._result_writer = None
        if not self._accepting_results:
            return
        error = asyncio.CancelledError() if task.cancelled() else task.exception()
        log.error(f'Circuit result writer stopped unexpectedly | Error:{error!r}')
        if self._result_writer is None:
            self._start_result_writer()

    async def _write_results(self) -> None:
        while True:
            queued = await self._result_queue.get()
            try:
                await self._write_result(queued)
            finally:
                self._result_queue.task_done()
                self._finish_pending_result(queued)

    async def _write_result(self, queued: _QueuedObservation) -> None:
        try:
            await self._record_observation(queued.decision, queued.observation)
        except asyncio.CancelledError:
            raise
        except (TimeoutError, RedisError, RuntimeError, ValueError) as exc:
            if not self._result_failure_logged:
                decision = queued.decision
                log.warning(
                    f'Circuit result write failed | Endpoint:{decision.endpoint_id}'
                    f' | Version:{decision.endpoint_version} | Outcome:{queued.observation.outcome.value}'
                    f' | Error:{exc!r}'
                )
                self._result_failure_logged = True
        except Exception as exc:
            decision = queued.decision
            log.error(
                f'Circuit result write failed unexpectedly | Endpoint:{decision.endpoint_id}'
                f' | Version:{decision.endpoint_version} | Outcome:{queued.observation.outcome.value}'
                f' | Error:{exc!r}'
            )
        else:
            self._result_failure_logged = False

    async def _record_observation(self, decision: CircuitDecision, observation: CircuitObservation) -> bool:
        key = make_key(decision.endpoint_id, decision.endpoint_version, decision.workload_class)
        cache_key = (decision.endpoint_id, decision.endpoint_version, decision.workload_class)
        cached = self._get_cached_state(cache_key)
        if cached is not None and (cached.record.state is not decision.state or cached.record.epoch != decision.epoch):
            return False
        outcome = observation.outcome
        if outcome in {CircuitOutcome.HARD_FAILURE, CircuitOutcome.SAMPLED_FAILURE, CircuitOutcome.THROTTLED}:
            self._cache.pop(cache_key, None)
        closed_success = decision.state is CircuitState.CLOSED and outcome is CircuitOutcome.SUCCESS
        if closed_success and decision.failures == 0 and cached is not None and cached.record.failures == 0:
            return True
        if closed_success:
            result = await self._record_success(key=key, decision=decision)
        else:
            async with self._hold_lock(cache_key):
                result = await self._record_locked(
                    key=key,
                    cache_key=cache_key,
                    decision=decision,
                    outcome=outcome,
                    throttle_seconds=self._throttle_seconds(observation),
                    cached=cached,
                )
        if closed_success and not result.applied and self._cache.get(cache_key) is cached:
            self._cache.pop(cache_key, None)
        elif not closed_success:
            self._cache_record(cache_key, result=result)
        self._log_transition(decision, result.record)
        return result.applied

    def _discard_results(self) -> None:
        discarded = 0
        while True:
            try:
                queued = self._result_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._result_queue.task_done()
            self._finish_pending_result(queued)
            discarded += 1
        if discarded:
            log.warning(f'Circuit results discarded during shutdown | Observations:{discarded}')

    def _finish_pending_result(self, queued: _QueuedObservation) -> None:
        decision = queued.decision
        key = (decision.endpoint_id, decision.endpoint_version, decision.workload_class)
        pending = self._pending_results.get(key, 0)
        if pending <= 1:
            self._pending_results.pop(key, None)
        else:
            self._pending_results[key] = pending - 1

    def _log_result_rejection(self, reason: str) -> None:
        if self._result_rejection_reason == reason:
            return
        self._result_rejection_reason = reason
        log.warning(f'Circuit result rejected | Reason:{reason}')

    async def _record_locked(
        self,
        *,
        key: str,
        cache_key: CircuitKey,
        decision: CircuitDecision,
        outcome: CircuitOutcome,
        throttle_seconds: int | None,
        cached: _CachedState | None,
    ) -> _StateResult:
        latest = self._get_cached_state(cache_key)
        if latest is not None and (latest.record.state is not decision.state or latest.record.epoch != decision.epoch):
            return _StateResult(
                record=latest.record,
                raw=latest.raw,
                redis_now=latest.redis_now,
                clock_anchor=latest.clock_anchor,
                applied=False,
            )
        initial = latest or cached
        return await self._apply_result(
            key=key,
            decision=decision,
            outcome=outcome,
            throttle_seconds=throttle_seconds,
            initial_raw=initial.raw if initial is not None else None,
            read_first=initial is None,
        )

    async def _admit_shared(
        self,
        *,
        key: str,
        endpoint_id: str,
        endpoint_version: int,
        workload_class: CircuitWorkloadClass,
    ) -> _StateResult:
        stored = await self._store.read(
            key,
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            workload_class=workload_class,
        )
        raw = stored.raw
        now: datetime | None = None
        clock_anchor: float | None = None
        while True:
            record = self._store.parse(
                raw,
                endpoint_id=endpoint_id,
                endpoint_version=endpoint_version,
                workload_class=workload_class,
            ).record
            if record.state is CircuitState.CLOSED:
                window = await self._window_store.get(
                    endpoint_id,
                    endpoint_version,
                    workload_class,
                    record.window_generation,
                )
                if window.samples < self._policy.window_min_samples or window.failure_rate < self._policy.window_failure_rate:
                    return _StateResult(record=record, raw=raw, redis_now=None, clock_anchor=None, applied=True)
                if now is None:
                    now, clock_anchor = await self._store.get_time()
                added = make_open(
                    self._policy,
                    record,
                    now=now,
                    failures=record.failures,
                    backoff_step=0,
                    reason=CircuitOpenReason.ERROR_RATE,
                )
                transition_time = now
                transition_anchor = clock_anchor
                cas = await self._store.compare_set(key, expected=raw, added=added)
                raw = cas.raw
                now = cas.redis_now
                clock_anchor = cas.clock_anchor
                if cas.applied:
                    log.warning(
                        f'Circuit opened by error rate | Endpoint:{endpoint_id} | Version:{endpoint_version}'
                        f' | Workload:{workload_class.value} | Samples:{window.samples}'
                        f' | FailureRate:{window.failure_rate:.4f}'
                    )
                    return _StateResult(
                        record=added,
                        raw=raw,
                        redis_now=transition_time,
                        clock_anchor=transition_anchor,
                        applied=False,
                    )
                continue
            if now is None:
                now, clock_anchor = await self._store.get_time()
            if record.state is CircuitState.OPEN:
                if record.retry_at is not None and record.retry_at > now:
                    return _StateResult(
                        record=record,
                        raw=raw,
                        redis_now=now,
                        clock_anchor=clock_anchor,
                        applied=False,
                    )
                added = grant_probe(self._policy, record, now=now, increment_epoch=True)
            elif record.probe_token is not None:
                if record.probe_until is not None and record.probe_until > now:
                    return _StateResult(
                        record=record,
                        raw=raw,
                        redis_now=now,
                        clock_anchor=clock_anchor,
                        applied=False,
                    )
                added = make_open(
                    self._policy,
                    record,
                    now=now,
                    failures=max(record.failures, self._policy.failure_threshold),
                    backoff_step=next_backoff_step(self._policy, record.backoff_step),
                    reason=CircuitOpenReason.HARD_FAILURE,
                )
            else:
                added = grant_probe(self._policy, record, now=now, increment_epoch=False)
            transition_time = now
            transition_anchor = clock_anchor
            cas = await self._store.compare_set(key, expected=raw, added=added)
            raw = cas.raw
            now = cas.redis_now
            clock_anchor = cas.clock_anchor
            if cas.applied:
                allowed = added.state is CircuitState.HALF_OPEN
                return _StateResult(
                    record=added,
                    raw=raw,
                    redis_now=transition_time,
                    clock_anchor=transition_anchor,
                    applied=allowed,
                )

    async def _record_success(self, *, key: str, decision: CircuitDecision) -> _StateResult:
        stored = await self._store.read(
            key,
            endpoint_id=decision.endpoint_id,
            endpoint_version=decision.endpoint_version,
            workload_class=decision.workload_class,
        )
        record = stored.record
        if record.state is not decision.state or record.epoch != decision.epoch:
            return _StateResult(record=record, raw=stored.raw, redis_now=None, clock_anchor=None, applied=False)
        if record.failures == 0:
            return _StateResult(record=record, raw=stored.raw, redis_now=None, clock_anchor=None, applied=True)
        return await self._apply_result(
            key=key,
            decision=decision,
            outcome=CircuitOutcome.SUCCESS,
            throttle_seconds=None,
            initial_raw=stored.raw,
            read_first=False,
        )

    async def _apply_result(
        self,
        *,
        key: str,
        decision: CircuitDecision,
        outcome: CircuitOutcome,
        throttle_seconds: int | None,
        initial_raw: CircuitRaw,
        read_first: bool,
    ) -> _StateResult:
        if read_first:
            stored = await self._store.read(
                key,
                endpoint_id=decision.endpoint_id,
                endpoint_version=decision.endpoint_version,
                workload_class=decision.workload_class,
            )
            raw = stored.raw
        else:
            raw = initial_raw
        now: datetime | None = None
        clock_anchor: float | None = None
        while True:
            record = self._store.parse(
                raw,
                endpoint_id=decision.endpoint_id,
                endpoint_version=decision.endpoint_version,
                workload_class=decision.workload_class,
            ).record
            stale = record.state is not decision.state or record.epoch != decision.epoch
            wrong_probe = record.state is CircuitState.HALF_OPEN and record.probe_token != decision.probe_token
            if stale or wrong_probe:
                return _StateResult(
                    record=record,
                    raw=raw,
                    redis_now=now,
                    clock_anchor=clock_anchor,
                    applied=False,
                )
            if record.state is CircuitState.CLOSED and outcome is CircuitOutcome.SUCCESS and record.failures == 0:
                return _StateResult(
                    record=record,
                    raw=raw,
                    redis_now=now,
                    clock_anchor=clock_anchor,
                    applied=True,
                )
            if now is None:
                now, clock_anchor = await self._store.get_time()
            if record.state is CircuitState.HALF_OPEN and (record.probe_until is None or record.probe_until <= now):
                return _StateResult(
                    record=record,
                    raw=raw,
                    redis_now=now,
                    clock_anchor=clock_anchor,
                    applied=False,
                )
            added = apply_outcome(
                self._policy,
                record,
                outcome=outcome,
                now=now,
                throttle_seconds=throttle_seconds,
            )
            transition_time = now
            transition_anchor = clock_anchor
            cas = await self._store.compare_set(key, expected=raw, added=added)
            raw = cas.raw
            now = cas.redis_now
            clock_anchor = cas.clock_anchor
            if cas.applied:
                return _StateResult(
                    record=added,
                    raw=raw,
                    redis_now=transition_time,
                    clock_anchor=transition_anchor,
                    applied=True,
                )

    def _throttle_seconds(self, observation: CircuitObservation) -> int | None:
        if observation.outcome is not CircuitOutcome.THROTTLED:
            return None
        wanted = observation.retry_after_seconds or self._policy.throttle_seconds
        return min(max(1, wanted), self._policy.throttle_max_seconds)

    @staticmethod
    def _log_transition(decision: CircuitDecision, record: CircuitRecord) -> None:
        if record.state is decision.state and record.open_reason is decision.open_reason:
            return
        log.warning(
            f'Circuit transition | Endpoint:{record.endpoint_id} | Version:{record.endpoint_version}'
            f' | Workload:{record.workload_class.value} | From:{decision.state.value} | To:{record.state.value}'
            f' | Reason:{record.open_reason.value if record.open_reason is not None else "recovered"}'
            f' | RetryAt:{record.retry_at.isoformat() if record.retry_at is not None else "none"}'
        )

    @asynccontextmanager
    async def _hold_lock(self, key: CircuitKey) -> AsyncIterator[None]:
        entry = self._locks.get(key)
        if entry is None:
            entry = _LockEntry(lock=asyncio.Lock())
            self._locks[key] = entry
        entry.users += 1
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            entry.users -= 1
            if entry.users == 0 and self._locks.get(key) is entry:
                self._locks.pop(key)

    def _get_cached_state(self, key: CircuitKey) -> _CachedState | None:
        cached = self._cache.get(key)
        if cached is None:
            return None
        if cached.expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return cached

    def _get_cached_decision(self, key: CircuitKey) -> CircuitDecision | None:
        cached = self._get_cached_state(key)
        if cached is None or cached.decision_expires_at <= time.monotonic():
            return None
        return cached.decision

    def _cache_record(
        self,
        key: CircuitKey,
        *,
        result: _StateResult,
        decision: CircuitDecision | None = None,
    ) -> None:
        now = time.monotonic()
        expires_at = now + self._policy.cache_ttl_ms / 1000
        cached_decision: CircuitDecision | None = None
        decision_expires_at = now
        if result.record.state is CircuitState.CLOSED and result.record.failures == 0:
            cached_decision = decision or make_decision(result.record, allowed=True)
            decision_expires_at = expires_at
        elif (
            result.record.state is CircuitState.OPEN
            and result.record.retry_at is not None
            and result.redis_now is not None
            and result.clock_anchor is not None
        ):
            remaining = max(0.0, (result.record.retry_at - result.redis_now).total_seconds())
            cached_decision = make_decision(result.record, allowed=False)
            decision_expires_at = min(expires_at, result.clock_anchor + remaining)
        elif (
            result.record.state is CircuitState.HALF_OPEN
            and result.record.probe_token is not None
            and result.record.probe_until is not None
            and result.redis_now is not None
            and result.clock_anchor is not None
        ):
            remaining = max(0.0, (result.record.probe_until - result.redis_now).total_seconds())
            cached_decision = make_decision(result.record, allowed=False)
            decision_expires_at = min(expires_at, result.clock_anchor + remaining)
        self._put_cached(
            key,
            _CachedState(
                decision=cached_decision,
                decision_expires_at=decision_expires_at,
                record=result.record,
                raw=result.raw,
                redis_now=result.redis_now,
                clock_anchor=result.clock_anchor,
                expires_at=expires_at,
            ),
        )

    def _put_cached(self, key: CircuitKey, cached: _CachedState) -> None:
        if self._policy.cache_ttl_ms == 0:
            return
        if key not in self._cache and len(self._cache) >= self._policy.cache_max_items:
            self._cache.pop(next(iter(self._cache)), None)
        self._cache[key] = cached
