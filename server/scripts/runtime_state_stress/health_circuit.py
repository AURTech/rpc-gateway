import asyncio
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.model.runtime_state.circuit import (
    CircuitObservation,
    CircuitOutcome,
    CircuitPolicy,
    CircuitState,
    CircuitWorkloadClass,
)
from app.model.runtime_state.endpoint.health import (
    EndpointHealth,
    HealthFailure,
    HealthObservation,
    HealthOrigin,
    HealthStatus,
)
from app.services.runtime_state.circuit.manager import CircuitManager
from app.services.runtime_state.endpoint.health.dispatcher import HealthDispatcher
from app.services.runtime_state.endpoint.health.manager import HealthManager
from app.services.runtime_state.endpoint.health.state import HealthBatch
from redis.asyncio import Redis
from scripts.runtime_state_stress.metrics import LatencyStats, ScenarioReport, scenario_report
from scripts.runtime_state_stress.scenarios import StressShape


async def _wait_health(dispatcher: HealthDispatcher, *, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    named_peak = 0
    while dispatcher.pending_batches:
        named = sum(task.get_name() == 'runtime-health-dispatcher' for task in asyncio.all_tasks() if not task.done())
        named_peak = max(named_peak, named)
        if time.monotonic() >= deadline:
            raise TimeoutError('Health dispatcher did not drain before the stress deadline.')
        await asyncio.sleep(0.01)
    return named_peak


def _health_observation(
    *,
    endpoint_id: str,
    endpoint_version: int,
    success: bool,
    observed_at: datetime,
    latency_ms: float | None = None,
) -> HealthObservation:
    return HealthObservation(
        endpoint_id=endpoint_id,
        endpoint_version=endpoint_version,
        origin=HealthOrigin.TRAFFIC,
        success=success,
        failure=None if success else HealthFailure.TIMEOUT,
        latency_ms=latency_ms,
        observed_at=observed_at,
    )


async def _health_phase(
    manager: HealthManager,
    *,
    endpoint_count: int,
    users: int,
    samples: int,
    success: bool,
    latency: LatencyStats,
) -> tuple[int, int]:
    async def writer(batch: HealthBatch) -> EndpointHealth:
        started_at = time.monotonic()
        result = await manager.record_batch(batch)
        latency.add(time.monotonic() - started_at)
        return result

    dispatcher = HealthDispatcher(max_batches=endpoint_count * 2, writer=writer)
    accepted = 0
    await dispatcher.start()

    async def submit_user(user_id: int) -> None:
        nonlocal accepted
        operations = endpoint_count * samples
        for operation in range(user_id, operations, users):
            endpoint_number = operation % endpoint_count
            sample = operation // endpoint_count
            observation = _health_observation(
                endpoint_id=f'health-{endpoint_number:04d}',
                endpoint_version=1,
                success=success,
                observed_at=datetime.now(UTC),
                latency_ms=10 + endpoint_number % 10 if success else None,
            )
            accepted += dispatcher.submit(observation)
            if sample % 4 == 0:
                await asyncio.sleep(0)

    try:
        await asyncio.gather(*(submit_user(user_id) for user_id in range(users)))
        named_peak = await _wait_health(dispatcher, timeout_seconds=30)
    finally:
        await dispatcher.close(drain_seconds=5)
    return accepted, named_peak


async def stress_health(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    manager = HealthManager(redis_client)
    endpoint_count = min(shape.endpoint_count, 128)
    failed_accepted, first_task_peak = await _health_phase(
        manager,
        endpoint_count=endpoint_count,
        users=shape.users,
        samples=3,
        success=False,
        latency=latency,
    )
    unhealthy = 0
    for endpoint_number in range(endpoint_count):
        health = await manager.get(f'health-{endpoint_number:04d}', 1)
        unhealthy += health is not None and health.status is HealthStatus.UNHEALTHY

    recovered_accepted, second_task_peak = await _health_phase(
        manager,
        endpoint_count=endpoint_count,
        users=shape.users,
        samples=12,
        success=True,
        latency=latency,
    )
    healthy = 0
    complete_samples = 0
    for endpoint_number in range(endpoint_count):
        health = await manager.get(f'health-{endpoint_number:04d}', 1)
        healthy += health is not None and health.status is HealthStatus.HEALTHY
        complete_samples += health is not None and health.samples == 15

    version_id = 'health-version'
    version_one = _health_observation(
        endpoint_id=version_id,
        endpoint_version=1,
        success=True,
        latency_ms=5,
        observed_at=datetime.now(UTC),
    )
    version_two = version_one.model_copy(
        update={'endpoint_version': 2, 'observed_at': version_one.observed_at + timedelta(microseconds=1)}
    )
    await manager.record(version_one)
    await manager.record(version_two)
    old_version = await manager.get(version_id, 1)
    new_version = await manager.get(version_id, 2)
    named_final = sum(task.get_name() == 'runtime-health-dispatcher' for task in asyncio.all_tasks() if not task.done())
    operations = endpoint_count * 15 + 2
    return scenario_report(
        name='endpoint_health_shared_window',
        started_at=started_at,
        operations=operations,
        latency=latency,
        counts={
            'endpoints': endpoint_count,
            'failure_submissions_accepted': failed_accepted,
            'recovery_submissions_accepted': recovered_accepted,
            'unhealthy_after_failures': unhealthy,
            'healthy_after_recovery': healthy,
            'complete_sample_windows': complete_samples,
        },
        checks={
            'all_failure_observations_accepted': failed_accepted == endpoint_count * 3,
            'failure_threshold_reached': unhealthy == endpoint_count,
            'all_recovery_observations_accepted': recovered_accepted == endpoint_count * 12,
            'recovery_threshold_reached': healthy == endpoint_count,
            'window_aggregation_complete': complete_samples == endpoint_count,
            'endpoint_version_isolated': old_version is None and new_version is not None,
            'health_dispatcher_task_fixed': max(first_task_peak, second_task_peak) <= 1,
            'health_dispatcher_task_closed': named_final == 0,
        },
        details={
            'runtime_health_task_peak': max(first_task_peak, second_task_peak),
            'runtime_health_task_final': named_final,
            'window_samples_per_endpoint': 15,
        },
    )


async def stress_circuit(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    endpoint_count = min(shape.endpoint_count, 64)
    policy = CircuitPolicy(
        failure_threshold=3,
        window_seconds=10,
        window_bucket_seconds=1,
        window_min_samples=5,
        window_failure_rate=0.6,
        open_seconds=1,
        recovery_successes=2,
        probe_seconds=2,
        max_open_seconds=2,
        cache_ttl_ms=0,
        operation_timeout_ms=2000,
        state_ttl_seconds=60,
    )
    writer = CircuitManager(redis_client, policy)
    shared = CircuitManager(redis_client, policy)
    outcomes: Counter[str] = Counter()
    await writer.start()
    await shared.start()

    async def fail_endpoint(worker_id: int) -> None:
        for endpoint_number in range(worker_id, endpoint_count, shape.users):
            endpoint_id = f'circuit-{endpoint_number:04d}'
            for _ in range(policy.failure_threshold):
                operation_started = time.monotonic()
                decision = await writer.before_attempt(endpoint_id, 1)
                accepted = writer.submit(decision, CircuitObservation(outcome=CircuitOutcome.HARD_FAILURE))
                latency.add(time.monotonic() - operation_started)
                outcomes['failures_accepted'] += accepted

    await asyncio.gather(*(fail_endpoint(worker_id) for worker_id in range(shape.users)))
    await writer.drain_results(timeout_seconds=5)
    open_count = 0
    denied_count = 0
    isolated_versions = 0
    for endpoint_number in range(endpoint_count):
        endpoint_id = f'circuit-{endpoint_number:04d}'
        snapshot = await shared.get(endpoint_id, 1)
        open_count += snapshot.state is CircuitState.OPEN
        denied_count += not (await shared.before_attempt(endpoint_id, 1)).allowed
        isolated_versions += (await shared.before_attempt(endpoint_id, 2)).state is CircuitState.CLOSED

    await asyncio.sleep(1.1)
    recovered = 0
    single_probe = 0
    for endpoint_number in range(endpoint_count):
        endpoint_id = f'circuit-{endpoint_number:04d}'
        contenders = [CircuitManager(redis_client, policy) for _ in range(4)]
        try:
            await asyncio.gather(*(manager.start() for manager in contenders))
            decisions = await asyncio.gather(*(manager.before_attempt(endpoint_id, 1) for manager in contenders))
            winners = [(manager, decision) for manager, decision in zip(contenders, decisions, strict=True) if decision.allowed]
            single_probe += len(winners) == 1
            if len(winners) != 1:
                continue
            winner, first_decision = winners[0]
            first_accepted = winner.submit(first_decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
            await winner.drain_results(timeout_seconds=5)
            second_decision = await shared.before_attempt(endpoint_id, 1)
            second_accepted = shared.submit(second_decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
            await shared.drain_results(timeout_seconds=5)
            snapshot = await shared.get(endpoint_id, 1)
            recovered += first_accepted and second_accepted and snapshot.state is CircuitState.CLOSED
        finally:
            await asyncio.gather(*(manager.close(drain_seconds=1) for manager in contenders))

    scoped_endpoint = 'circuit-workload-isolation'
    trace_failures = 5
    for _ in range(trace_failures):
        decision = await writer.before_scoped_attempt(scoped_endpoint, 1, CircuitWorkloadClass.TRACE)
        writer.submit(decision, CircuitObservation(outcome=CircuitOutcome.SAMPLED_FAILURE))
    await writer.drain_results(timeout_seconds=5)
    deadline = time.monotonic() + 5
    while writer.pending_window_observations and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    trace_decision = await shared.before_scoped_attempt(scoped_endpoint, 1, CircuitWorkloadClass.TRACE)
    standard_decision = await shared.before_attempt(scoped_endpoint, 1)
    trace_snapshot = await shared.get(scoped_endpoint, 1, CircuitWorkloadClass.TRACE)
    standard_snapshot = await shared.get(scoped_endpoint, 1, CircuitWorkloadClass.STANDARD)
    await writer.close(drain_seconds=2)
    await shared.close(drain_seconds=2)

    operations = endpoint_count * (policy.failure_threshold + 10)
    return scenario_report(
        name='circuit_breaker_shared_transitions',
        started_at=started_at,
        operations=operations,
        latency=latency,
        counts={
            'endpoints': endpoint_count,
            'failure_results_accepted': outcomes['failures_accepted'],
            'open': open_count,
            'denied_while_open': denied_count,
            'single_half_open_probe': single_probe,
            'recovered_closed': recovered,
            'isolated_versions': isolated_versions,
            'trace_window_samples': trace_failures,
        },
        checks={
            'failure_threshold_applied': outcomes['failures_accepted'] == endpoint_count * policy.failure_threshold,
            'all_circuits_opened': open_count == endpoint_count,
            'open_circuits_denied': denied_count == endpoint_count,
            'endpoint_versions_isolated': isolated_versions == endpoint_count,
            'cluster_probe_singleton': single_probe == endpoint_count,
            'two_probe_recovery_closed': recovered == endpoint_count,
            'trace_error_rate_opened': not trace_decision.allowed and trace_snapshot.state is CircuitState.OPEN,
            'standard_workload_isolated': standard_decision.allowed and standard_snapshot.state is CircuitState.CLOSED,
        },
        details={
            'failure_threshold': policy.failure_threshold,
            'recovery_successes': policy.recovery_successes,
            'contenders_per_half_open': 4,
        },
    )
