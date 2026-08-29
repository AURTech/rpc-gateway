import asyncio
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import orjson
from app.model.blockchain import CHAIN_CATALOG, Chain, Network
from app.model.jsonrpc_forwarding import (
    JsonRpcForwardingFailure,
    JsonRpcForwardingFailureCode,
    JsonRpcForwardingResult,
    JsonRpcForwardingSuccess,
)
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.model.system_cache import (
    CacheEntry,
    CacheFlightLease,
    CacheKey,
    CachePolicy,
    CacheTier,
)
from app.model.system_jsonrpc_cache import SystemJsonRpcCacheResult
from app.services.system_cache.limits import MAX_WAITERS
from app.services.system_jsonrpc_cache import SystemJsonRpcCacheManager
from app.services.system_jsonrpc_cache.manager import JsonRpcLoader
from app.services.system_jsonrpc_cache.policy import SystemJsonRpcCachePolicy
from scripts.system_cache_stress.report import ScenarioReport


class MemoryStore:
    def __init__(self, *, fail_reads: bool = False) -> None:
        self.entries: dict[CacheKey, CacheEntry] = {}
        self.reads = 0
        self.writes = 0
        self.refreshes = 0
        self.fail_reads = fail_reads
        self.fences: dict[CacheKey, int] = {}

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        self.reads += 1
        if self.fail_reads:
            raise RuntimeError('Injected cache read failure.')
        return self.entries.get(policy.key)

    async def put(self, entry: CacheEntry) -> None:
        self.writes += 1
        self.entries[entry.key] = entry

    async def refresh(self, entry: CacheEntry) -> None:
        self.refreshes += 1
        saved = self.entries.get(entry.key)
        if saved is not None:
            self.entries[entry.key] = CacheEntry(
                key=saved.key,
                tier=saved.tier,
                payload=saved.payload,
                fresh_until=entry.fresh_until,
                stale_until=entry.stale_until,
                sequence=saved.sequence,
            )

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        if self.fences.get(entry.key, 0) > lease.fence:
            return False
        self.fences[entry.key] = lease.fence
        if refresh:
            await self.refresh(entry)
        else:
            await self.put(entry)
        return True


class CountingLoader:
    def __init__(self, *, delay_seconds: float, payload_bytes: int = 64) -> None:
        self.delay_seconds = delay_seconds
        self.payload_bytes = payload_bytes
        self.calls = 0
        self.active = 0
        self.peak_active = 0

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del chain, network
        self.calls += 1
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            await asyncio.sleep(self.delay_seconds)
            if call.method == 'eth_blockNumber':
                result: object = '0x100'
            else:
                height = call.params[0] if isinstance(call.params, list) and call.params else '0x100'
                result = {'number': height, 'blob': 'x' * self.payload_bytes}
            response = JsonRpcSuccessResponse(jsonrpc='2.0', id=call.request_id(), result=orjson.dumps(result))
            return JsonRpcForwardingSuccess(response=response)
        finally:
            self.active -= 1


class FailingLoader:
    def __init__(self, *, delay_seconds: float = 0) -> None:
        self.calls = 0
        self.delay_seconds = delay_seconds

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingFailure:
        del chain, network, call
        self.calls += 1
        await asyncio.sleep(self.delay_seconds)
        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)


class NullLoader:
    def __init__(self, *, delay_seconds: float) -> None:
        self.calls = 0
        self.delay_seconds = delay_seconds

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del chain, network
        self.calls += 1
        await asyncio.sleep(self.delay_seconds)
        return JsonRpcForwardingSuccess(response=JsonRpcSuccessResponse(jsonrpc='2.0', id=call.request_id(), result=b'null'))


class LocalDistributedFlight:
    async def acquire(self, key: CacheKey) -> CacheFlightLease:
        del key
        return CacheFlightLease(token='winner', fence=1)

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        del key, lease

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        del key, lease
        return True

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool:
        del key, timeout_seconds
        return True


class FailingDistributedFlight(LocalDistributedFlight):
    async def acquire(self, key: CacheKey) -> CacheFlightLease:
        del key
        raise RuntimeError('Injected distributed flight failure.')


def _policy(retention_seconds: Mapping[Chain, int]) -> SystemJsonRpcCachePolicy:
    return SystemJsonRpcCachePolicy(redis_ttl_ms=250, postgres_retention_seconds=retention_seconds)


class _LoadedManager:
    def __init__(self, manager: SystemJsonRpcCacheManager, loader: JsonRpcLoader) -> None:
        self._manager = manager
        self._loader = loader

    async def get_result(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> bytes | JsonRpcForwardingResult | None:
        return await self._manager.get_result(chain=chain, network=network, call=call, loader=self._loader)

    async def get_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
    ) -> SystemJsonRpcCacheResult:
        return await self._manager.get_result_with_usage(
            chain=chain,
            network=network,
            call=call,
            loader=self._loader,
        )

    async def close(self) -> None:
        await self._manager.close(drain_seconds=1)


def _manager(
    store: MemoryStore,
    loader: JsonRpcLoader,
    policies: SystemJsonRpcCachePolicy,
    *,
    flight: LocalDistributedFlight | None = None,
) -> _LoadedManager:
    manager = SystemJsonRpcCacheManager.create(
        store,
        policies,
        flight or LocalDistributedFlight(),
        flight_wait_seconds=2,
    )
    return _LoadedManager(manager, loader)


async def stress_same_key(retention_seconds: Mapping[Chain, int], *, concurrency: int) -> ScenarioReport:
    started_at = time.monotonic()
    store = MemoryStore()
    loader = CountingLoader(delay_seconds=1.2)
    manager = _manager(store, loader, _policy(retention_seconds))
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    first = await asyncio.gather(
        *(manager.get_result_with_usage(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call) for _ in range(concurrency))
    )
    await asyncio.sleep(0.03)
    second = [
        await manager.get_result_with_usage(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
        for _ in range(concurrency)
    ]
    checks = {
        'all_results_equal': len({result.value for result in [*first, *second]}) == 1 and first[0].value is not None,
        'cold_leader_is_only_miss': sum(result.hit for result in first) == concurrency - 1,
        'warm_reads_are_all_hits': all(result.hit for result in second),
        'one_upstream_load': loader.calls == 1,
        'one_cache_write': store.writes == 1,
        'locked_recheck_and_warm_reads_exact': store.reads == concurrency + 2,
        'one_active_loader': loader.peak_active == 1,
    }
    await manager.close()
    return ScenarioReport(
        name='same_key_local_singleflight',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'concurrency': concurrency,
            'cold_hits': sum(result.hit for result in first),
            'warm_hits': sum(result.hit for result in second),
            'loads': loader.calls,
            'reads': store.reads,
            'writes': store.writes,
        },
    )


async def stress_failure_singleflight_accounting(
    retention_seconds: Mapping[Chain, int],
    *,
    concurrency: int,
) -> ScenarioReport:
    started_at = time.monotonic()
    store = MemoryStore()
    loader = FailingLoader(delay_seconds=0.05)
    manager = _manager(store, loader, _policy(retention_seconds))
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    results = await asyncio.gather(
        *(manager.get_result_with_usage(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call) for _ in range(concurrency))
    )
    expected = JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED)
    checks = {
        'one_upstream_attempt': loader.calls == 1,
        'all_followers_reuse_failure': all(result.value == expected for result in results),
        'reused_failures_are_not_hits': not any(result.hit for result in results),
        'failure_not_stored': store.writes == 0,
    }
    await manager.close()
    return ScenarioReport(
        name='failure_singleflight_accounting',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'concurrency': concurrency,
            'loads': loader.calls,
            'hits': sum(result.hit for result in results),
            'writes': store.writes,
        },
    )


async def stress_null_singleflight_accounting(
    retention_seconds: Mapping[Chain, int],
    *,
    concurrency: int,
) -> ScenarioReport:
    started_at = time.monotonic()
    store = MemoryStore()
    loader = NullLoader(delay_seconds=0.05)
    manager = _manager(store, loader, _policy(retention_seconds))
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])
    results = await asyncio.gather(
        *(manager.get_result_with_usage(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call) for _ in range(concurrency))
    )
    checks = {
        'one_upstream_attempt': loader.calls == 1,
        'all_followers_reuse_null': all(result.value == b'null' for result in results),
        'reused_null_is_not_hit': not any(result.hit for result in results),
        'null_not_stored': store.writes == 0,
    }
    await manager.close()
    return ScenarioReport(
        name='null_singleflight_accounting',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'concurrency': concurrency,
            'loads': loader.calls,
            'hits': sum(result.hit for result in results),
            'writes': store.writes,
        },
    )


async def stress_large_payload_same_key(
    retention_seconds: Mapping[Chain, int],
    *,
    concurrency: int,
    payload_bytes: int,
) -> ScenarioReport:
    started_at = time.monotonic()
    store = MemoryStore()
    loader = CountingLoader(delay_seconds=0.03, payload_bytes=payload_bytes)
    manager = _manager(store, loader, _policy(retention_seconds))
    call = JsonRpcCall(
        jsonrpc='2.0',
        id=1,
        method='getBlock',
        params=[100, {'encoding': 'json', 'rewards': False, 'commitment': 'finalized'}],
    )
    results = await asyncio.gather(
        *(manager.get_result(chain=Chain.SOLANA, network=Network.MAINNET_BETA, call=call) for _ in range(concurrency))
    )
    first = results[0]
    checks = {
        'all_requests_completed': first is not None and all(result is not None for result in results),
        'one_upstream_load': loader.calls == 1,
        'one_cache_write': store.writes == 1,
        'one_active_loader': loader.peak_active == 1,
        'waiters_share_payload_object': first is not None and all(result is first for result in results),
        'representative_payload_size': isinstance(first, bytes) and len(first) >= payload_bytes,
    }
    await manager.close()
    return ScenarioReport(
        name='large_payload_same_key_singleflight',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={
            'concurrency': concurrency,
            'loads': loader.calls,
            'writes': store.writes,
            'payload_bytes': len(first) if isinstance(first, bytes) else 0,
        },
    )


async def stress_distinct_key_concurrency(retention_seconds: Mapping[Chain, int]) -> ScenarioReport:
    started_at = time.monotonic()
    store = MemoryStore()
    loader = CountingLoader(delay_seconds=0.08)
    manager = _manager(store, loader, _policy(retention_seconds))
    calls = [
        JsonRpcCall(jsonrpc='2.0', id=height, method='eth_getBlockByNumber', params=[hex(height), False])
        for height in range(100, 112)
    ]
    results = await asyncio.gather(
        *(manager.get_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call) for call in calls)
    )
    completed = sum(result is not None for result in results)
    checks = {
        'all_distinct_keys_loaded': loader.calls == len(calls),
        'all_requests_completed': completed == len(calls),
        'loads_can_overlap': loader.peak_active > 4,
    }
    await manager.close()
    return ScenarioReport(
        name='distinct_key_concurrency',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'requests': len(calls), 'completed': completed, 'loads': loader.calls, 'peak_active': loader.peak_active},
    )


async def stress_waiter_capacity(retention_seconds: Mapping[Chain, int]) -> ScenarioReport:
    started_at = time.monotonic()
    store = MemoryStore()
    loader = CountingLoader(delay_seconds=0.05)
    manager = _manager(store, loader, _policy(retention_seconds))
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    requests = MAX_WAITERS + 64
    results = await asyncio.gather(
        *(manager.get_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call) for _ in range(requests))
    )
    completed = sum(result is not None for result in results)
    checks = {
        'one_upstream_load': loader.calls == 1,
        'waiter_limit_exact': completed == MAX_WAITERS + 1,
        'overflow_failed_open': requests - completed == 63,
        'one_active_loader': loader.peak_active == 1,
    }
    await manager.close()
    return ScenarioReport(
        name='same_key_waiter_capacity',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'requests': requests, 'completed': completed, 'rejected': requests - completed, 'loads': loader.calls},
    )


async def stress_limits_and_failure(retention_seconds: Mapping[Chain, int]) -> ScenarioReport:
    started_at = time.monotonic()
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])
    large_store = MemoryStore()
    large_loader = CountingLoader(delay_seconds=0, payload_bytes=2048)
    large_manager = _manager(
        large_store,
        large_loader,
        _policy(retention_seconds),
    )
    large_result = await large_manager.get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
    )
    failed_store = MemoryStore(fail_reads=True)
    fallback_loader = CountingLoader(delay_seconds=0)
    fallback_manager = _manager(failed_store, fallback_loader, _policy(retention_seconds))
    fallback_result = await fallback_manager.get_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    failed_flight_manager = _manager(
        MemoryStore(),
        CountingLoader(delay_seconds=0),
        _policy(retention_seconds),
        flight=FailingDistributedFlight(),
    )
    failed_flight_result = await failed_flight_manager.get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
    )
    checks = {
        'large_payload_returned': large_result is not None,
        'large_payload_stored': large_store.writes == 1,
        'store_failure_uses_loader': fallback_result is not None and fallback_loader.calls == 1,
        'flight_failure_returns_none': failed_flight_result is None,
    }
    await asyncio.gather(large_manager.close(), fallback_manager.close(), failed_flight_manager.close())
    return ScenarioReport(
        name='limits_and_fail_open',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'large_payload_writes': large_store.writes, 'fallback_loads': fallback_loader.calls},
    )


async def stress_stale_fallback(retention_seconds: Mapping[Chain, int]) -> ScenarioReport:
    started_at = time.monotonic()
    policies = _policy(retention_seconds)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)
    if policy is None:
        raise RuntimeError('Stress Redis TTL policy is unavailable.')
    now = datetime.now(UTC)
    stale_payload = b'"0x100"'
    stale_entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=stale_payload,
        fresh_until=now - timedelta(seconds=1),
        stale_until=now + timedelta(seconds=2),
        sequence=None,
    )
    stale_store = MemoryStore()
    stale_store.entries[policy.key] = stale_entry
    stale_loader = FailingLoader()
    stale_manager = _manager(stale_store, stale_loader, policies)
    stale_result = await stale_manager.get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
    )

    expired_store = MemoryStore()
    expired_store.entries[policy.key] = CacheEntry(
        key=policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=stale_payload,
        fresh_until=now - timedelta(seconds=2),
        stale_until=now - timedelta(seconds=1),
        sequence=None,
    )
    expired_loader = FailingLoader()
    expired_manager = _manager(expired_store, expired_loader, policies)
    expired_result = await expired_manager.get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
    )
    checks = {
        'stale_returned_on_upstream_failure': stale_result == stale_payload,
        'expired_stale_returns_loader_failure': expired_result
        == JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED),
        'upstream_attempted': stale_loader.calls == 1 and expired_loader.calls == 1,
    }
    await asyncio.gather(stale_manager.close(), expired_manager.close())
    return ScenarioReport(
        name='stale_fallback_on_upstream_failure',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'stale_loader_calls': stale_loader.calls, 'expired_loader_calls': expired_loader.calls},
    )


def check_direct_policies(retention_seconds: Mapping[Chain, int]) -> ScenarioReport:
    started_at = time.monotonic()
    calls = {
        Chain.ETHEREUM: JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x1', False]),
        Chain.SOLANA: JsonRpcCall(
            jsonrpc='2.0',
            id=2,
            method='getBlock',
            params=[1, {'encoding': 'jsonParsed', 'rewards': False, 'commitment': 'finalized'}],
        ),
        Chain.BITCOIN: JsonRpcCall(jsonrpc='2.0', id=3, method='getblockhash', params=[1]),
    }
    policies = _policy(retention_seconds)
    classified: dict[Chain, CachePolicy | None] = {}
    for chain, call in calls.items():
        policy = policies.classify(chain=chain, network=next(iter(CHAIN_CATALOG[chain].networks)), call=call)
        classified[chain] = policy
    ethereum = classified[Chain.ETHEREUM]
    solana = classified[Chain.SOLANA]
    bitcoin = classified[Chain.BITCOIN]
    checks = {
        'evm_postgres_retention': ethereum is not None and ethereum.tier is CacheTier.POSTGRES_RETENTION,
        'svm_postgres_retention': solana is not None and solana.tier is CacheTier.POSTGRES_RETENTION,
        'utxo_hash_redis_ttl': (
            bitcoin is not None
            and bitcoin.tier is CacheTier.REDIS_TTL
            and bitcoin.ttl_ms == retention_seconds[Chain.BITCOIN] * 1000
        ),
    }
    latest_call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['latest', False])
    latest_policy = policies.classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=latest_call)
    checks['latest_full_block_excluded'] = latest_policy is None
    return ScenarioReport(
        name='direct_cache_policies',
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
        checks=checks,
        counts={'classified': sum(policy is not None for policy in classified.values())},
    )


async def run_core(
    retention_seconds: Mapping[Chain, int],
    *,
    concurrency: int,
    large_payload_concurrency: int,
    payload_bytes: int,
) -> list[ScenarioReport]:
    return [
        check_direct_policies(retention_seconds),
        await stress_same_key(retention_seconds, concurrency=concurrency),
        await stress_failure_singleflight_accounting(retention_seconds, concurrency=concurrency),
        await stress_null_singleflight_accounting(retention_seconds, concurrency=concurrency),
        await stress_large_payload_same_key(
            retention_seconds,
            concurrency=large_payload_concurrency,
            payload_bytes=payload_bytes,
        ),
        await stress_distinct_key_concurrency(retention_seconds),
        await stress_waiter_capacity(retention_seconds),
        await stress_limits_and_failure(retention_seconds),
        await stress_stale_fallback(retention_seconds),
    ]
