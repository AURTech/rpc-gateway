import asyncio
import time
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import orjson
from app.core.config import CONF
from app.model.blockchain import Chain, Network
from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse
from app.model.runtime_state.circuit import CircuitObservation, CircuitOutcome, CircuitPolicy, CircuitState
from app.model.runtime_state.endpoint.health import EndpointHealth, HealthObservation, HealthOrigin
from app.model.runtime_state.endpoint.tip import TipObservation
from app.model.runtime_state.tip import Finality, TipUnit
from app.services.public.jsonrpc.tip import extract_tip
from app.services.runtime_state.chain.tip.manager import ChainTipManager
from app.services.runtime_state.chain.tip.store import ChainTipStore
from app.services.runtime_state.circuit.manager import CircuitManager
from app.services.runtime_state.endpoint.health.dispatcher import HealthDispatcher
from app.services.runtime_state.endpoint.health.manager import HealthManager
from app.services.runtime_state.endpoint.health.state import HealthBatch
from app.services.runtime_state.endpoint.tip.dispatcher import (
    TIP_MAX_RETRY_AGE_SECONDS,
    TIP_MAX_RETRY_ATTEMPTS,
    TipDispatcher,
)
from app.services.runtime_state.endpoint.tip.manager import TipManager
from app.services.runtime_state.endpoint.tip.store import TipStore
from app.services.runtime_state.endpoint.tip.write import TipWriteResult
from redis.asyncio import Redis
from redis.exceptions import RedisError
from scripts.runtime_state_stress.metrics import LatencyStats, ScenarioReport, scenario_report
from scripts.runtime_state_stress.runtime_config import LEASE_SECONDS, REDIS_IO_MS, RENEW_THRESHOLD_SECONDS
from scripts.runtime_state_stress.scenarios import StressShape


async def _wait_tips(dispatcher: TipDispatcher, *, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    named_peak = 0
    while dispatcher.pending_items:
        named = sum(
            task.get_name() in {'runtime-tip-writer', 'runtime-tip-retry'} for task in asyncio.all_tasks() if not task.done()
        )
        named_peak = max(named_peak, named)
        if time.monotonic() >= deadline:
            raise TimeoutError('Tip dispatcher did not drain before the scenario deadline.')
        await asyncio.sleep(0.01)
    return named_peak


async def _wait_health(dispatcher: HealthDispatcher, *, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    named_peak = 0
    while dispatcher.pending_batches:
        named = sum(task.get_name() == 'runtime-health-dispatcher' for task in asyncio.all_tasks() if not task.done())
        named_peak = max(named_peak, named)
        if time.monotonic() >= deadline:
            raise TimeoutError('Health dispatcher did not drain before the mixed-load deadline.')
        await asyncio.sleep(0.01)
    return named_peak


def _extract_observation(*, sequence: int, endpoint_id: str) -> TipObservation:
    observed_at = datetime.now(UTC)
    call = JsonRpcCall(jsonrpc='2.0', method='eth_blockNumber', id=sequence)
    response = JsonRpcSuccessResponse(id=sequence, result=orjson.dumps(hex(40_000_000 + sequence)))
    tip = extract_tip(
        chain=Chain.POLYGON,
        network=Network.MAINNET,
        call=call,
        response=response,
        observed_at=observed_at,
    )
    if tip is None:
        raise RuntimeError('The EVM Tip extractor rejected a valid stress response.')
    return TipObservation.from_tip(tip, endpoint_id=endpoint_id, endpoint_version=1)


async def stress_mixed(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    endpoint_count = min(shape.endpoint_count, 1024)
    manager = TipManager(TipStore(redis_client))
    health_manager = HealthManager(redis_client)
    circuit_manager = CircuitManager(redis_client, CircuitPolicy(operation_timeout_ms=2000))
    write_results: Counter[TipWriteResult] = Counter()
    health_latency = LatencyStats()

    async def writer(observation: TipObservation) -> TipWriteResult:
        write_started = time.monotonic()
        result = await manager.record(observation)
        latency.add(time.monotonic() - write_started)
        write_results[result] += 1
        return result

    async def write_health(batch: HealthBatch) -> EndpointHealth:
        write_started = time.monotonic()
        result = await health_manager.record_batch(batch)
        health_latency.add(time.monotonic() - write_started)
        return result

    dispatcher = TipDispatcher(writer=writer, max_items=endpoint_count)
    health_dispatcher = HealthDispatcher(
        max_batches=CONF.RUNTIME_HEALTH_DISPATCHER_MAX_BATCHES,
        writer=write_health,
    )
    chain_manager = ChainTipManager(manager, ChainTipStore(redis_client, max_redis_io_ms=REDIS_IO_MS))
    expected: dict[str, TipObservation] = {}
    accepted = 0
    extracted = 0
    page_reads = 0
    duplicate_pages = 0
    chain_reads = 0
    chain_values = 0
    health_accepted = 0
    circuit_allowed = 0
    circuit_results = 0
    circuit_denied = 0
    stop_readers = asyncio.Event()
    sequence = 0
    sequence_lock = asyncio.Lock()
    await dispatcher.start()
    await health_dispatcher.start()
    await circuit_manager.start()
    deadline = time.monotonic() + shape.mixed_seconds

    async def submit_user() -> None:
        nonlocal accepted, circuit_allowed, circuit_denied, circuit_results, extracted, health_accepted, sequence
        while time.monotonic() < deadline:
            async with sequence_lock:
                operation = sequence
                sequence += 1
            endpoint_id = f'mixed-{operation % endpoint_count:04d}'
            decision = await circuit_manager.before_attempt(endpoint_id, 1)
            if not decision.allowed:
                circuit_denied += 1
                await asyncio.sleep(0)
                continue
            circuit_allowed += 1
            observation = _extract_observation(sequence=operation, endpoint_id=endpoint_id)
            extracted += 1
            if dispatcher.submit(observation):
                accepted += 1
                saved = expected.get(endpoint_id)
                if saved is None or observation.observed_at > saved.observed_at:
                    expected[endpoint_id] = observation
            health_accepted += health_dispatcher.submit(
                HealthObservation(
                    endpoint_id=endpoint_id,
                    endpoint_version=1,
                    origin=HealthOrigin.TRAFFIC,
                    success=True,
                    latency_ms=10 + operation % 20,
                    observed_at=observation.observed_at,
                )
            )
            result_accepted = circuit_manager.submit(decision, CircuitObservation(outcome=CircuitOutcome.SUCCESS))
            circuit_results += result_accepted
            if operation % 64 == 0:
                await asyncio.sleep(0)

    async def read_pages() -> None:
        nonlocal duplicate_pages, page_reads
        while not stop_readers.is_set():
            endpoints: set[str] = set()
            async for observation in manager.iterate(
                chain=Chain.POLYGON,
                network=Network.MAINNET,
                unit=TipUnit.BLOCK,
                finality=Finality.LATEST,
            ):
                if observation.endpoint_id in endpoints:
                    duplicate_pages += 1
                endpoints.add(observation.endpoint_id)
            page_reads += 1
            await asyncio.sleep(0)

    async def read_chain() -> None:
        nonlocal chain_reads, chain_values
        while not stop_readers.is_set():
            tip = await chain_manager.get_tip(
                chain=Chain.POLYGON,
                network=Network.MAINNET,
                unit=TipUnit.BLOCK,
                finality=Finality.LATEST,
            )
            chain_reads += 1
            chain_values += tip is not None
            await asyncio.sleep(0)

    reader_count = min(shape.users, 8)
    readers = [asyncio.create_task(read_pages()) for _ in range(reader_count)]
    readers.extend(asyncio.create_task(read_chain()) for _ in range(reader_count))
    users = [asyncio.create_task(submit_user()) for _ in range(shape.users)]
    try:
        await asyncio.gather(*users)
        stop_readers.set()
        await asyncio.gather(*readers)
        named_peak = await _wait_tips(dispatcher, timeout_seconds=30)
        health_task_peak = await _wait_health(health_dispatcher, timeout_seconds=30)
    finally:
        stop_readers.set()
        for task in (*users, *readers):
            if not task.done():
                task.cancel()
        await asyncio.gather(*users, return_exceptions=True)
        await asyncio.gather(*readers, return_exceptions=True)
        await dispatcher.close(drain_seconds=5)
        await health_dispatcher.close(drain_seconds=5)
        await circuit_manager.close(drain_seconds=5)

    mismatches = 0
    values: list[int] = []
    async for observation in manager.iterate(
        chain=Chain.POLYGON,
        network=Network.MAINNET,
        unit=TipUnit.BLOCK,
        finality=Finality.LATEST,
    ):
        values.append(observation.value)
        if expected.get(observation.endpoint_id) != observation:
            mismatches += 1
    await asyncio.sleep(1.1)
    chain_tip = await chain_manager.get_tip(
        chain=Chain.POLYGON,
        network=Network.MAINNET,
        unit=TipUnit.BLOCK,
        finality=Finality.LATEST,
    )
    values.sort()
    expected_median = values[(len(values) - 1) // 2] if values else None
    health_sources = 0
    circuit_closed = 0
    for endpoint_number in range(endpoint_count):
        endpoint_id = f'mixed-{endpoint_number:04d}'
        health_sources += await health_manager.get(endpoint_id, 1) is not None
        circuit_closed += (await circuit_manager.get(endpoint_id, 1)).state is CircuitState.CLOSED
    named_final = sum(
        task.get_name() in {'runtime-tip-writer', 'runtime-tip-retry'} for task in asyncio.all_tasks() if not task.done()
    )
    health_named_final = sum(task.get_name() == 'runtime-health-dispatcher' for task in asyncio.all_tasks() if not task.done())
    return scenario_report(
        name='mixed_extractor_tip_chain_soak' if shape.soak else 'mixed_extractor_tip_chain',
        started_at=started_at,
        operations=extracted + page_reads + chain_reads,
        latency=latency,
        counts={
            'extracted': extracted,
            'dispatcher_accepted': accepted,
            'stored': write_results[TipWriteResult.STORED],
            'page_reads': page_reads,
            'chain_reads': chain_reads,
            'chain_non_empty': chain_values,
            'final_sources': len(values),
            'health_accepted': health_accepted,
            'health_sources': health_sources,
            'circuit_allowed': circuit_allowed,
            'circuit_results_applied': circuit_results,
            'circuit_denied': circuit_denied,
            'circuit_closed': circuit_closed,
        },
        checks={
            'extractor_produced_all_observations': extracted > 0,
            'dispatcher_accepted_observations': accepted > 0,
            'latest_endpoint_tips_preserved': mismatches == 0 and len(values) == endpoint_count,
            'concurrent_pages_unique': duplicate_pages == 0,
            'concurrent_page_reads_executed': page_reads > 0,
            'concurrent_chain_reads_executed': chain_reads > 0,
            'final_chain_tip_computed': chain_tip is not None,
            'final_chain_lower_median': chain_tip is not None and chain_tip.value == expected_median,
            'final_chain_source_count': chain_tip is not None and chain_tip.source_count == len(values),
            'health_combined_for_all_sources': health_sources == endpoint_count and health_accepted > 0,
            'health_submissions_not_rejected': health_accepted == extracted,
            'circuit_admission_for_all_requests': circuit_allowed == extracted and circuit_denied == 0,
            'circuit_results_recorded': circuit_results == circuit_allowed,
            'circuit_remained_closed': circuit_closed == endpoint_count,
            'mixed_dispatcher_tasks_fixed': named_peak <= 2,
            'mixed_dispatcher_tasks_closed': named_final == 0,
            'mixed_health_task_fixed': health_task_peak <= 1,
            'mixed_health_task_closed': health_named_final == 0,
        },
        details={
            'duration_seconds': shape.mixed_seconds,
            'endpoint_count': endpoint_count,
            'expected_lower_median': expected_median,
            'latest_mismatches': mismatches,
            'duplicate_page_members': duplicate_pages,
            'runtime_tip_task_peak': named_peak,
            'runtime_tip_task_final': named_final,
            'runtime_health_task_peak': health_task_peak,
            'runtime_health_task_final': health_named_final,
            'health_write_latency': health_latency.report(),
        },
    )


async def stress_outage(outage_url: str) -> ScenarioReport:
    started_at = time.monotonic()
    cpu_started = time.process_time()
    latency = LatencyStats()
    key_count = 1024
    calls: Counter[str] = Counter()
    outage_redis = Redis.from_url(
        outage_url,
        decode_responses=True,
        retry_on_timeout=False,
        socket_connect_timeout=CONF.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=CONF.REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        # Reason: redis.asyncio commands are awaitable at runtime; the ping stub includes a sync branch.
        available = await outage_redis.ping()  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
    except RedisError:
        available = False
    if available:
        await outage_redis.aclose()
        raise RuntimeError('The outage Redis URL is reachable; refusing to write any stress keys to it.')
    manager = TipManager(TipStore(outage_redis))

    async def unavailable_writer(observation: TipObservation) -> TipWriteResult:
        write_started = time.monotonic()
        calls[observation.endpoint_id] += 1
        try:
            return await manager.record(observation)
        finally:
            latency.add(time.monotonic() - write_started)

    dispatcher = TipDispatcher(writer=unavailable_writer, max_items=key_count)
    admitted = 0
    await dispatcher.start()
    try:
        for key in range(key_count):
            observation = _extract_observation(sequence=key, endpoint_id=f'outage-{key:04d}')
            admitted += dispatcher.submit(observation)
        named_peak = await _wait_tips(dispatcher, timeout_seconds=TIP_MAX_RETRY_AGE_SECONDS + 2)
    finally:
        await dispatcher.close(drain_seconds=1)
        await outage_redis.aclose()
    elapsed = time.monotonic() - started_at
    cpu_seconds = time.process_time() - cpu_started
    call_counts = list(calls.values())
    named_final = sum(
        task.get_name() in {'runtime-tip-writer', 'runtime-tip-retry'} for task in asyncio.all_tasks() if not task.done()
    )
    return scenario_report(
        name='dispatcher_real_redis_outage',
        started_at=started_at,
        operations=sum(call_counts),
        latency=latency,
        counts={
            'keys': key_count,
            'admitted': admitted,
            'writer_calls': sum(call_counts),
            'redis_connection_failure_events': sum(call_counts),
            'min_calls_per_key': min(call_counts, default=0),
            'max_calls_per_key': max(call_counts, default=0),
        },
        checks={
            'all_outage_keys_admitted': admitted == key_count,
            'all_outage_keys_attempted': len(call_counts) == key_count and min(call_counts, default=0) >= 1,
            'outage_retries_bounded': max(call_counts, default=0) <= TIP_MAX_RETRY_ATTEMPTS + 1,
            'outage_failure_events_bounded': sum(call_counts) <= key_count * (TIP_MAX_RETRY_ATTEMPTS + 1),
            'outage_age_bounded': elapsed <= TIP_MAX_RETRY_AGE_SECONDS + 2,
            'outage_pending_drained': dispatcher.pending_items == 0,
            'outage_tasks_fixed': named_peak <= 2,
            'outage_tasks_closed': named_final == 0,
        },
        details={
            'retry_attempt_limit': TIP_MAX_RETRY_ATTEMPTS,
            'retry_age_limit_seconds': TIP_MAX_RETRY_AGE_SECONDS,
            'elapsed_seconds': round(elapsed, 6),
            'process_cpu_seconds': round(cpu_seconds, 6),
            'process_cpu_percent_one_core': round(cpu_seconds / elapsed * 100, 3),
            'runtime_tip_task_peak': named_peak,
            'runtime_tip_task_final': named_final,
            'log_capture': 'not measured; dispatcher log aggregation is outside this script contract',
        },
    )


class PageBoundaryStallReader:
    def __init__(self, *, stall_seconds: float, source_count: int = 256) -> None:
        self._stall_seconds = stall_seconds
        self._source_count = source_count

    async def iterate(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> AsyncIterator[TipObservation]:
        await asyncio.sleep(self._stall_seconds)
        observed_at = datetime.now(UTC)
        for source in range(self._source_count):
            yield TipObservation(
                endpoint_id=f'page-stall-{source:04d}',
                endpoint_version=1,
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
                value=50_000_000 + source,
                observed_at=observed_at,
            )


async def stress_page_stall(redis_client: Redis, *, stall_seconds: float = 5.5) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    source_count = 256
    manager = ChainTipManager(
        PageBoundaryStallReader(stall_seconds=stall_seconds, source_count=source_count),
        ChainTipStore(redis_client, max_redis_io_ms=REDIS_IO_MS),
    )
    read_started = time.monotonic()
    tip = await manager.get_tip(
        chain=Chain.POLYGON,
        network=Network.AMOY,
        unit=TipUnit.BLOCK,
        finality=Finality.SAFE,
    )
    latency.add(time.monotonic() - read_started)
    elapsed = time.monotonic() - read_started
    expected = 50_000_000 + (source_count - 1) // 2
    return scenario_report(
        name='chain_tip_no_yield_page_boundary',
        started_at=started_at,
        operations=source_count,
        latency=latency,
        counts={'sources': source_count, 'snapshots': int(tip is not None)},
        checks={
            'no_yield_delay_exceeded_renew_threshold': elapsed > RENEW_THRESHOLD_SECONDS,
            'no_yield_delay_below_derived_lease': elapsed < LEASE_SECONDS,
            'boundary_snapshot_committed': tip is not None,
            'boundary_lower_median': tip is not None and tip.value == expected,
            'boundary_source_count': tip is not None and tip.source_count == source_count,
        },
        details={
            'synthetic_no_yield_seconds': stall_seconds,
            'elapsed_seconds': round(elapsed, 6),
            'redis_io_ms': REDIS_IO_MS,
            'derived_lease_seconds': LEASE_SECONDS,
            'scope': 'reader page boundary delay; this does not emulate a Redis socket stall',
        },
    )
