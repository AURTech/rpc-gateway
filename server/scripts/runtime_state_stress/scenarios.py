import asyncio
import time
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.model.blockchain import Chain, Network
from app.model.runtime_state.chain.tip import ChainTip
from app.model.runtime_state.endpoint.tip import TipObservation
from app.model.runtime_state.tip import Finality, TipUnit
from app.services.runtime_state.chain.tip.manager import ChainTipManager
from app.services.runtime_state.chain.tip.store import ChainTipStore
from app.services.runtime_state.endpoint.tip.dispatcher import TipDispatcher
from app.services.runtime_state.endpoint.tip.manager import TipManager
from app.services.runtime_state.endpoint.tip.store import MAX_ENDPOINTS, TipStore
from app.services.runtime_state.endpoint.tip.write import TipWriteResult
from redis.asyncio import Redis
from scripts.runtime_state_stress.metrics import LatencyStats, ScenarioReport, scenario_report
from scripts.runtime_state_stress.runtime_config import LEASE_SECONDS, REDIS_IO_MS, RENEW_THRESHOLD_SECONDS


@dataclass(frozen=True, slots=True, kw_only=True)
class StressShape:
    users: int
    endpoint_count: int
    dispatcher_operations: int
    chain_readers: int
    renewal_seconds: float
    mixed_seconds: float
    soak: bool


async def _wait_dispatcher(dispatcher: TipDispatcher, *, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    named_peak = 0
    while dispatcher.pending_items:
        named = sum(
            task.get_name() in {'runtime-tip-writer', 'runtime-tip-retry'} for task in asyncio.all_tasks() if not task.done()
        )
        named_peak = max(named_peak, named)
        if time.monotonic() >= deadline:
            raise TimeoutError('Tip dispatcher did not drain before the stress deadline.')
        await asyncio.sleep(0.01)
    return named_peak


def _observation(
    *,
    endpoint_id: str,
    value: int,
    observed_at: datetime,
    network: Network = Network.MAINNET,
    finality: Finality = Finality.LATEST,
) -> TipObservation:
    return TipObservation(
        endpoint_id=endpoint_id,
        endpoint_version=1,
        chain=Chain.ETHEREUM,
        network=network,
        unit=TipUnit.BLOCK,
        finality=finality,
        value=value,
        observed_at=observed_at,
    )


async def stress_dispatcher(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    results: Counter[TipWriteResult] = Counter()
    manager = TipManager(TipStore(redis_client))

    async def writer(tip: TipObservation) -> TipWriteResult:
        write_started = time.monotonic()
        result = await manager.record(tip)
        latency.add(time.monotonic() - write_started)
        results[result] += 1
        return result

    dispatcher_endpoints = min(shape.endpoint_count, 1024)
    dispatcher = TipDispatcher(writer=writer, max_items=dispatcher_endpoints)
    expected: dict[str, TipObservation] = {}
    accepted = 0
    rejected = 0
    submitted = 0
    base_time = datetime.now(UTC)
    await dispatcher.start()

    async def submit_user(user_id: int) -> None:
        nonlocal accepted, rejected, submitted
        for sequence in range(user_id, shape.dispatcher_operations, shape.users):
            endpoint_id = f'dispatch-{sequence % dispatcher_endpoints:05d}'
            tip = _observation(
                endpoint_id=endpoint_id,
                value=1_000_000 + sequence,
                observed_at=base_time + timedelta(microseconds=sequence),
            )
            submitted += 1
            if dispatcher.submit(tip):
                accepted += 1
                saved = expected.get(endpoint_id)
                if saved is None or tip.observed_at > saved.observed_at:
                    expected[endpoint_id] = tip
            else:
                rejected += 1
            if sequence % 64 == 0:
                await asyncio.sleep(0)

    try:
        await asyncio.gather(*(submit_user(user_id) for user_id in range(shape.users)))
        oldest = _observation(endpoint_id='dispatch-00000', value=1, observed_at=base_time - timedelta(seconds=1))
        stale_results_before = results[TipWriteResult.STALE_NOOP]
        stale_submit_accepted = dispatcher.submit(oldest)
        named_peak = await _wait_dispatcher(dispatcher, timeout_seconds=30)
    finally:
        await dispatcher.close(drain_seconds=5)

    mismatches = 0
    for endpoint_id, wanted in expected.items():
        saved = await manager.get(
            endpoint_id=endpoint_id,
            chain=wanted.chain,
            network=wanted.network,
            unit=wanted.unit,
            finality=wanted.finality,
        )
        if saved != wanted:
            mismatches += 1

    first = next(iter(expected.values()))
    stale = first.model_copy(update={'observed_at': base_time - timedelta(seconds=2)})
    stale_result = await manager.record(stale)
    future = first.model_copy(
        update={'endpoint_id': 'dispatch-future', 'observed_at': datetime.now(UTC) + timedelta(seconds=10)}
    )
    future_result = await manager.record(future)
    named_final = sum(
        task.get_name() in {'runtime-tip-writer', 'runtime-tip-retry'} for task in asyncio.all_tasks() if not task.done()
    )
    counts = {result.value: results[result] for result in TipWriteResult}
    counts.update({'submitted': submitted, 'accepted': accepted, 'admission_rejected': rejected})
    checks = {
        'latest_observation_preserved': mismatches == 0,
        'stale_submit_safely_completed': (
            not stale_submit_accepted or results[TipWriteResult.STALE_NOOP] > stale_results_before
        ),
        'stale_result_structured': stale_result is TipWriteResult.STALE_NOOP,
        'future_result_structured': future_result is TipWriteResult.FUTURE_REJECTED,
        'pending_drained': dispatcher.pending_items == 0,
        'dispatcher_task_count_fixed': named_peak <= 2,
        'dispatcher_tasks_closed': named_final == 0,
    }
    return scenario_report(
        name='tip_dispatcher',
        started_at=started_at,
        operations=submitted,
        latency=latency,
        counts=counts,
        checks=checks,
        details={
            'dispatcher_endpoints': dispatcher_endpoints,
            'verified_endpoints': len(expected),
            'mismatches': mismatches,
            'runtime_tip_task_peak': named_peak,
            'runtime_tip_task_final': named_final,
        },
    )


async def stress_endpoint_store(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    results: Counter[TipWriteResult] = Counter()
    manager = TipManager(TipStore(redis_client))
    observed_at = datetime.now(UTC)

    async def write_worker(worker_id: int) -> None:
        for endpoint_number in range(worker_id, shape.endpoint_count, shape.users):
            tip = _observation(
                endpoint_id=f'store-{endpoint_number:05d}',
                value=10_000_000 + endpoint_number,
                observed_at=observed_at,
                network=Network.SEPOLIA,
            )
            write_started = time.monotonic()
            result = await manager.record(tip)
            latency.add(time.monotonic() - write_started)
            results[result] += 1

    await asyncio.gather(*(write_worker(worker_id) for worker_id in range(shape.users)))
    capacity_result: TipWriteResult | None = None
    if shape.endpoint_count == MAX_ENDPOINTS:
        over_cap = _observation(
            endpoint_id='store-over-cap',
            value=99_999_999,
            observed_at=observed_at,
            network=Network.SEPOLIA,
        )
        capacity_result = await manager.record(over_cap)

    seen = bytearray(shape.endpoint_count)
    invalid_ids = 0
    duplicates = 0
    listed = 0
    async for tip in manager.iterate(
        chain=Chain.ETHEREUM,
        network=Network.SEPOLIA,
        unit=TipUnit.BLOCK,
        finality=Finality.LATEST,
    ):
        listed += 1
        try:
            endpoint_number = int(tip.endpoint_id.removeprefix('store-'))
        except ValueError:
            invalid_ids += 1
            continue
        if not 0 <= endpoint_number < shape.endpoint_count:
            invalid_ids += 1
            continue
        if seen[endpoint_number]:
            duplicates += 1
        seen[endpoint_number] = 1

    missing = seen.count(0)
    counts = {result.value: results[result] for result in TipWriteResult}
    counts.update({'requested': shape.endpoint_count, 'listed': listed})
    checks = {
        'all_writes_stored': results[TipWriteResult.STORED] == shape.endpoint_count,
        'paged_results_unique': duplicates == 0,
        'paged_results_complete': missing == 0 and invalid_ids == 0 and listed == shape.endpoint_count,
        'capacity_enforced_if_reached': capacity_result is None or capacity_result is TipWriteResult.CAPACITY_REJECTED,
    }
    return scenario_report(
        name='endpoint_tip_store',
        started_at=started_at,
        operations=shape.endpoint_count + int(capacity_result is not None),
        latency=latency,
        counts=counts,
        checks=checks,
        details={
            'store_limit': MAX_ENDPOINTS,
            'capacity_result': capacity_result.value if capacity_result is not None else 'not_reached',
            'duplicates': duplicates,
            'missing': missing,
            'invalid_ids': invalid_ids,
            'verification_bitmap_bytes': len(seen),
        },
    )


async def _timed_chain_read(manager: ChainTipManager, latency: LatencyStats) -> ChainTip | None:
    started_at = time.monotonic()
    tip = await manager.get_tip(
        chain=Chain.ETHEREUM,
        network=Network.SEPOLIA,
        unit=TipUnit.BLOCK,
        finality=Finality.LATEST,
    )
    latency.add(time.monotonic() - started_at)
    return tip


async def stress_chain_tip(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    reader = TipManager(TipStore(redis_client))
    manager = ChainTipManager(reader, ChainTipStore(redis_client, max_redis_io_ms=REDIS_IO_MS))
    cold_results = await asyncio.gather(*(_timed_chain_read(manager, latency) for _ in range(shape.chain_readers)))
    warm_results = await asyncio.gather(*(_timed_chain_read(manager, latency) for _ in range(shape.chain_readers)))
    worker_managers = [
        ChainTipManager(reader, ChainTipStore(redis_client, max_redis_io_ms=REDIS_IO_MS)) for _ in range(shape.chain_readers)
    ]
    worker_results = await asyncio.gather(*(_timed_chain_read(worker, latency) for worker in worker_managers))
    expected_value = 10_000_000 + (shape.endpoint_count - 1) // 2

    def is_expected(tip: ChainTip | None) -> bool:
        return tip is not None and tip.value == expected_value and tip.source_count == shape.endpoint_count

    correct_cold = sum(is_expected(tip) for tip in cold_results)
    correct_warm = sum(is_expected(tip) for tip in warm_results)
    correct_workers = sum(is_expected(tip) for tip in worker_results)

    fence_store = ChainTipStore(redis_client, max_redis_io_ms=25, lock_ttl_ms=100)
    stale_rejected = False
    newer_applied = False
    fence_advanced = False
    async with fence_store.lock(
        chain=Chain.ETHEREUM,
        network=Network.SEPOLIA,
        unit=TipUnit.BLOCK,
        finality=Finality.SAFE,
    ) as stale_lease:
        if stale_lease is not None:
            await asyncio.sleep(0.15)
            async with fence_store.lock(
                chain=Chain.ETHEREUM,
                network=Network.SEPOLIA,
                unit=TipUnit.BLOCK,
                finality=Finality.SAFE,
            ) as newer_lease:
                if newer_lease is not None:
                    fence_advanced = newer_lease.fence > stale_lease.fence
                    newer_tip = ChainTip(
                        chain=Chain.ETHEREUM,
                        network=Network.SEPOLIA,
                        unit=TipUnit.BLOCK,
                        finality=Finality.SAFE,
                        value=expected_value,
                        source_count=3,
                        observed_at=newer_lease.clock.now,
                        computed_at=newer_lease.clock.now,
                        valid_until=newer_lease.clock.now + timedelta(seconds=30),
                    )
                    newer_applied = (await fence_store.put(newer_tip, lease=newer_lease)).applied
                    stale_rejected = not (await fence_store.put(newer_tip, lease=stale_lease)).applied

    counts = {
        'cold_reads': shape.chain_readers,
        'cold_correct': correct_cold,
        'cold_empty': sum(tip is None for tip in cold_results),
        'warm_reads': shape.chain_readers,
        'warm_correct': correct_warm,
        'warm_worker_reads': shape.chain_readers,
        'warm_worker_correct': correct_workers,
    }
    checks = {
        'cold_single_flight_shared_result': correct_cold == shape.chain_readers,
        'warm_snapshot_consistent': correct_warm == shape.chain_readers,
        'warm_cross_worker_snapshot_consistent': correct_workers == shape.chain_readers,
        'lower_median_correct': all(is_expected(tip) for tip in warm_results),
        'fence_advanced_after_expiry': fence_advanced,
        'newer_fence_applied': newer_applied,
        'stale_fence_rejected': stale_rejected,
    }
    return scenario_report(
        name='chain_tip_cold_warm',
        started_at=started_at,
        operations=shape.chain_readers * 3 + 2,
        latency=latency,
        counts=counts,
        checks=checks,
        details={
            'expected_lower_median': expected_value,
            'expected_source_count': shape.endpoint_count,
            'cold_contract': 'same-process callers wait at most one second for the caller-owned single-flight winner',
            'cold_empty': sum(tip is None for tip in cold_results),
        },
    )


class _SlowReader:
    def __init__(self, *, source_count: int, duration_seconds: float) -> None:
        self._source_count = source_count
        self._delay = duration_seconds / source_count

    async def iterate(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> AsyncIterator[TipObservation]:
        for source in range(self._source_count):
            await asyncio.sleep(self._delay)
            yield TipObservation(
                endpoint_id=f'slow-{source:04d}',
                endpoint_version=1,
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
                value=20_000_000 + source,
                observed_at=datetime.now(UTC),
            )


async def stress_lease_renewal(redis_client: Redis, shape: StressShape) -> ScenarioReport:
    started_at = time.monotonic()
    latency = LatencyStats()
    source_count = 768
    manager = ChainTipManager(
        _SlowReader(source_count=source_count, duration_seconds=shape.renewal_seconds),
        ChainTipStore(redis_client, max_redis_io_ms=REDIS_IO_MS),
    )
    read_started = time.monotonic()
    tip = await manager.get_tip(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        unit=TipUnit.BLOCK,
        finality=Finality.FINALIZED,
    )
    latency.add(time.monotonic() - read_started)
    elapsed = time.monotonic() - read_started
    expected = 20_000_000 + (source_count - 1) // 2
    checks = {
        'aggregation_exceeded_renew_threshold': elapsed > RENEW_THRESHOLD_SECONDS,
        'aggregation_remained_within_lease': elapsed < LEASE_SECONDS,
        'renewed_lease_committed': tip is not None,
        'slow_lower_median_correct': tip is not None and tip.value == expected,
        'slow_source_count_correct': tip is not None and tip.source_count == source_count,
    }
    return scenario_report(
        name='chain_tip_lease_renewal',
        started_at=started_at,
        operations=source_count,
        latency=latency,
        counts={'sources': source_count, 'snapshots': int(tip is not None)},
        checks=checks,
        details={
            'requested_renewal_seconds': shape.renewal_seconds,
            'observed_seconds': round(elapsed, 6),
            'renew_threshold_seconds': RENEW_THRESHOLD_SECONDS,
            'derived_lease_seconds': LEASE_SECONDS,
        },
    )
