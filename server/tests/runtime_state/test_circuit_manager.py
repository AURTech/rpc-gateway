import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.errors import UnavailableError
from app.model.runtime_state.circuit import (
    CircuitDecision,
    CircuitObservation,
    CircuitOutcome,
    CircuitPolicy,
    CircuitState,
)
from app.services.runtime_state.circuit import CircuitManager
from redis.asyncio import Redis


@pytest.mark.anyio
async def test_circuit_waiter_can_reuse_decision_after_redis_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis), CircuitPolicy(operation_timeout_ms=10))
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.CLOSED,
        failures=0,
        epoch=0,
    )
    cached = False

    def get_cached(_key: tuple[str, int]) -> CircuitDecision | None:
        return decision if cached else None

    monkeypatch.setattr(manager, '_get_cached_decision', get_cached)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def timeout_admission(**_kwargs: object) -> None:
        entered.set()
        await release.wait()
        raise TimeoutError

    monkeypatch.setattr(manager, '_admit_shared', timeout_admission)
    holder = asyncio.create_task(manager.before_attempt('endpoint-a', 1))
    await entered.wait()
    waiter = asyncio.create_task(manager.before_attempt('endpoint-a', 1))
    await asyncio.sleep(0)
    cached = True
    release.set()

    with pytest.raises(UnavailableError, match='Circuit state is unavailable'):
        await holder
    assert await waiter == decision


@pytest.mark.anyio
async def test_circuit_admission_timeout_releases_local_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis), CircuitPolicy(operation_timeout_ms=10))
    blocked = asyncio.Event()

    async def block_admission(**_kwargs: object) -> None:
        await blocked.wait()

    monkeypatch.setattr(manager, '_admit_shared', block_admission)

    with pytest.raises(UnavailableError, match='Circuit state is unavailable'):
        async with asyncio.timeout(1):
            await manager.before_attempt('endpoint-a', 1)

    assert manager._locks == {}


@pytest.mark.anyio
async def test_circuit_result_submission_does_not_wait_for_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_write(_decision: CircuitDecision, _observation: CircuitObservation) -> bool:
        started.set()
        await release.wait()
        return True

    monkeypatch.setattr(manager, '_record_observation', blocked_write)
    await manager.start()
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.HALF_OPEN,
        failures=5,
        epoch=1,
        probe_token='probe-a',
    )

    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    await asyncio.wait_for(started.wait(), timeout=1)
    assert manager.pending_result_observations == 0

    release.set()
    await manager.close(drain_seconds=1)


@pytest.mark.anyio
async def test_circuit_result_writer_preserves_submission_order(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    outcomes: list[CircuitOutcome] = []

    async def record_in_order(_decision: CircuitDecision, observation: CircuitObservation) -> bool:
        outcomes.append(observation.outcome)
        if len(outcomes) == 1:
            first_started.set()
            await release_first.wait()
        return True

    monkeypatch.setattr(manager, '_record_observation', record_in_order)
    await manager.start()
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.HALF_OPEN,
        failures=5,
        epoch=1,
        probe_token='probe-a',
    )

    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.HARD_FAILURE))
    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    await asyncio.wait_for(first_started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert outcomes == [CircuitOutcome.HARD_FAILURE]

    release_first.set()
    await manager.close(drain_seconds=1)
    assert outcomes == [CircuitOutcome.HARD_FAILURE, CircuitOutcome.SUCCESS]
    assert manager._pending_results == {}


@pytest.mark.anyio
async def test_success_resets_failures_queued_before_shared_write(
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = CircuitManager(test_redis, CircuitPolicy(cache_ttl_ms=1000, operation_timeout_ms=2000))
    original_write = manager._write_result
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    first = True

    async def block_first_write(queued: Any) -> None:
        nonlocal first
        if first:
            first = False
            first_started.set()
            await release_first.wait()
        await original_write(queued)

    monkeypatch.setattr(manager, '_write_result', block_first_write)
    await manager.start()
    endpoint_id = 'queued-failure-reset'
    decision = await manager.before_attempt(endpoint_id, 1)

    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.HARD_FAILURE))
    await asyncio.wait_for(first_started.wait(), timeout=1)
    refilled = await manager.before_attempt(endpoint_id, 1)
    assert refilled.failures == 0
    assert manager.submit(refilled, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    for _index in range(4):
        assert manager.submit(refilled, CircuitObservation(outcome=CircuitOutcome.HARD_FAILURE))
        assert manager.submit(refilled, CircuitObservation(outcome=CircuitOutcome.SUCCESS))

    release_first.set()
    await manager.drain_results(timeout_seconds=5)
    snapshot = await manager.get(endpoint_id, 1)
    await manager.close(drain_seconds=1)

    assert snapshot.state is CircuitState.CLOSED
    assert snapshot.failures == 0
    assert manager._pending_results == {}


@pytest.mark.anyio
async def test_unexpected_result_error_does_not_stop_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    calls = 0
    processed = asyncio.Event()

    async def fail_once(_decision: CircuitDecision, _observation: CircuitObservation) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise KeyError('invalid result')
        processed.set()
        return True

    monkeypatch.setattr(manager, '_record_observation', fail_once)
    await manager.start()
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.HALF_OPEN,
        failures=5,
        epoch=1,
        probe_token='probe-a',
    )

    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    await asyncio.wait_for(processed.wait(), timeout=1)
    await manager.drain_results(timeout_seconds=1)

    assert manager._result_writer is not None and not manager._result_writer.done()
    assert manager._pending_results == {}
    await manager.close(drain_seconds=1)


@pytest.mark.anyio
async def test_result_writer_restarts_after_task_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    original_writer = manager._write_results
    writer_starts = 0
    processed = asyncio.Event()

    async def crash_once() -> None:
        nonlocal writer_starts
        writer_starts += 1
        if writer_starts == 1:
            raise RuntimeError('writer crashed')
        await original_writer()

    async def record(_decision: CircuitDecision, _observation: CircuitObservation) -> bool:
        processed.set()
        return True

    monkeypatch.setattr(manager, '_write_results', crash_once)
    monkeypatch.setattr(manager, '_record_observation', record)
    await manager.start()
    async with asyncio.timeout(1):
        while writer_starts < 2:
            await asyncio.sleep(0)
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.HALF_OPEN,
        failures=5,
        epoch=1,
        probe_token='probe-a',
    )

    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    await asyncio.wait_for(processed.wait(), timeout=1)
    await manager.drain_results(timeout_seconds=1)

    assert manager._result_writer is not None and not manager._result_writer.done()
    await manager.close(drain_seconds=1)


@pytest.mark.anyio
async def test_result_capacity_and_shutdown_clear_pending_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    manager._result_queue = asyncio.Queue(maxsize=1)
    started = asyncio.Event()

    async def block(_decision: CircuitDecision, _observation: CircuitObservation) -> bool:
        started.set()
        await asyncio.Event().wait()
        return True

    monkeypatch.setattr(manager, '_record_observation', block)
    await manager.start()
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.HALF_OPEN,
        failures=5,
        epoch=1,
        probe_token='probe-a',
    )
    observation = CircuitObservation(outcome=CircuitOutcome.SUCCESS)

    assert manager.submit(decision, observation)
    await asyncio.wait_for(started.wait(), timeout=1)
    assert manager.submit(decision, observation)
    assert not manager.submit(decision, observation)
    assert sum(manager._pending_results.values()) == 2

    await manager.close(drain_seconds=0)

    assert manager._pending_results == {}
    assert manager.pending_result_observations == 0


def test_hard_failure_invalidates_local_circuit_cache_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.CLOSED,
        failures=0,
        epoch=0,
    )
    cache_key = ('endpoint-a', 1, decision.workload_class)
    monkeypatch.setattr(manager, '_get_cached_state', lambda _key: None)
    manager._cache[cache_key] = MagicMock()

    assert not manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.HARD_FAILURE))
    assert cache_key not in manager._cache


def test_healthy_closed_success_requires_no_result_write(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CircuitManager(MagicMock(spec=Redis))
    decision = CircuitDecision(
        endpoint_id='endpoint-a',
        endpoint_version=1,
        allowed=True,
        state=CircuitState.CLOSED,
        failures=0,
        epoch=0,
    )
    cached = MagicMock()
    cached.record.state = CircuitState.CLOSED
    cached.record.epoch = 0
    cached.record.failures = 0
    monkeypatch.setattr(manager, '_get_cached_state', lambda _key: cached)

    assert manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
    assert manager.pending_result_observations == 0
