import asyncio
from datetime import UTC, datetime, timedelta

import orjson
import pytest
from app.infra import redis as redis_keys
from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import JsonRpcForwardingSuccess
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.model.system_cache import CacheEntry, CacheFlightLease, CacheKey, CachePolicy, CacheTier
from app.model.transport import Transport
from app.services.system_cache.flight import PostgresRetentionFlight, RedisTtlFlight, flight_key
from app.services.system_cache.manager import SystemCacheManager
from app.services.system_cache.publisher import PostgresRetentionPublisher
from app.services.system_cache.store import PostgresRetentionStore, RedisTtlStore
from app.services.system_jsonrpc_cache import SystemJsonRpcCacheManager
from redis.asyncio import Redis
from tortoise import connections

pytestmark = pytest.mark.anyio


class _Store:
    def __init__(self) -> None:
        self.entry: CacheEntry | None = None
        self.writes = 0
        self.fence = 0

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        if self.entry is None or self.entry.key != policy.key:
            return None
        return self.entry

    async def put(self, entry: CacheEntry) -> None:
        self.writes += 1
        self.entry = entry

    async def refresh(self, entry: CacheEntry) -> None:
        self.writes += 1
        self.entry = entry

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        del refresh
        if lease.fence < self.fence:
            return False
        self.fence = lease.fence
        self.writes += 1
        self.entry = entry
        return True


class _AcquireRaceStore(_Store):
    def __init__(self, saved_after_acquire: CacheEntry) -> None:
        super().__init__()
        self.saved_after_acquire = saved_after_acquire
        self.reads = 0

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        del policy
        self.reads += 1
        return None if self.reads == 1 else self.saved_after_acquire


class _BlockingCommitStore(_Store):
    def __init__(self) -> None:
        super().__init__()
        self.commit_started = asyncio.Event()
        self.commit_cancelled = False

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        del entry, lease, refresh
        self.commit_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.commit_cancelled = True
            raise
        return False


class _IgnoringCancelStore(_Store):
    def __init__(self) -> None:
        super().__init__()
        self.commit_started = asyncio.Event()
        self.cancel_seen = asyncio.Event()
        self.release = asyncio.Event()
        self.completed = asyncio.Event()

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        del entry, lease, refresh
        self.commit_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancel_seen.set()
            await self.release.wait()
        finally:
            self.completed.set()
        return False


class _PolicyProvider:
    def __init__(self, policy: CachePolicy) -> None:
        self.policy = policy

    def classify(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> CachePolicy:
        del chain, network, call
        return self.policy


class _FlightCoordinator:
    def __init__(self) -> None:
        self.owner: CacheFlightLease | None = None
        self.generation = 0
        self.released = asyncio.Event()

    async def acquire(self, key: CacheKey) -> CacheFlightLease | None:
        del key
        if self.owner is not None:
            return None
        self.generation += 1
        self.owner = CacheFlightLease(token=f'owner-{self.generation}', fence=self.generation)
        self.released.clear()
        return self.owner

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        del key
        return self.owner == lease

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        del key
        if self.owner == lease:
            self.owner = None
            self.released.set()

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool:
        del key
        try:
            async with asyncio.timeout(timeout_seconds):
                await self.released.wait()
        except TimeoutError:
            return False
        return True

    def revoke(self) -> None:
        self.owner = None
        self.released.set()


class _LosingFlight(_FlightCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.renewals = 0

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        self.renewals += 1
        if self.renewals == 1:
            return await super().renew(key, lease)
        self.revoke()
        return False


class _BlockingReleaseFlight(_FlightCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.release_started = asyncio.Event()
        self.allow_release = asyncio.Event()

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        self.release_started.set()
        await self.allow_release.wait()
        await super().release(key, lease)


class _Loader:
    def __init__(self, result: object, *, blocked: bool = False) -> None:
        self.result = result
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del chain, network
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return JsonRpcForwardingSuccess(
            response=JsonRpcSuccessResponse(jsonrpc='2.0', id=call.request_id(), result=orjson.dumps(self.result)),
        )


def _policy(
    *,
    tier: CacheTier,
    ttl_ms: int | None,
    sequence: int | None,
    digest: str = '1' * 40,
) -> CachePolicy:
    return CachePolicy(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            operation='eth_blockNumber' if sequence is None else 'eth_getBlockByNumber',
            digest=digest,
        ),
        tier=tier,
        retention_seconds=3600 if tier is CacheTier.POSTGRES_RETENTION else None,
        ttl_ms=ttl_ms,
        sequence=sequence,
    )


def _manager(
    store: _Store,
    policy: CachePolicy,
    flight: _FlightCoordinator,
) -> SystemJsonRpcCacheManager:
    core = SystemCacheManager(store, flight, flight_wait_seconds=2)
    return SystemJsonRpcCacheManager(
        core,
        _PolicyProvider(policy),
    )


async def test_large_results_are_stored_in_both_tiers() -> None:
    large_result = 'x' * (8 * 1024 * 1024 + 1)
    redis_store = _Store()
    redis_policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    redis_call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    redis_result = await _manager(
        redis_store,
        redis_policy,
        _FlightCoordinator(),
    ).get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=redis_call,
        loader=_Loader(large_result),
    )

    postgres_store = _Store()
    postgres_policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    postgres_call = JsonRpcCall(jsonrpc='2.0', id=2, method='eth_getBlockByNumber', params=['0x64', False])
    postgres_manager = _manager(
        postgres_store,
        postgres_policy,
        _FlightCoordinator(),
    )
    postgres_result = await postgres_manager.get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=postgres_call,
        loader=_Loader({'number': '0x64', 'blob': large_result}),
    )
    await postgres_manager.close(drain_seconds=1)

    assert redis_result is not None
    assert redis_store.writes == 1
    assert redis_store.entry is not None and len(redis_store.entry.payload) > 8 * 1024 * 1024
    assert postgres_result is not None
    assert postgres_store.writes == 1
    assert postgres_store.entry is not None and len(postgres_store.entry.payload) > 8 * 1024 * 1024


async def test_lost_owner_cannot_overwrite_newer_redis_ttl_entry() -> None:
    store = _Store()
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = _FlightCoordinator()
    old_loader = _Loader('0x64', blocked=True)
    new_loader = _Loader('0x65')
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])

    old_task = asyncio.create_task(
        _manager(store, policy, flight).get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=old_loader,
        )
    )
    await asyncio.wait_for(old_loader.started.wait(), timeout=1)
    flight.revoke()
    new_result = await asyncio.wait_for(
        _manager(store, policy, flight).get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=new_loader,
        ),
        timeout=1,
    )
    assert new_result == b'"0x65"'
    assert store.entry is not None and store.entry.payload == b'"0x65"'

    old_loader.release.set()
    await asyncio.wait_for(old_task, timeout=1)

    assert store.entry is not None and store.entry.payload == b'"0x65"'


async def test_postgres_retention_entry_remains_reusable_without_tip_window() -> None:
    store = _Store()
    policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    store.entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=orjson.dumps({'number': '0x64', 'hash': 'old'}),
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )
    loader = _Loader({'number': '0x64', 'hash': 'new'})
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])

    result = await _manager(store, policy, _FlightCoordinator()).get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
        loader=loader,
    )

    assert result == orjson.dumps({'number': '0x64', 'hash': 'old'})
    assert loader.calls == 0


async def test_cached_reads_remain_available_during_another_load() -> None:
    store = _Store()
    leader_policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    policies = _PolicyProvider(leader_policy)
    flight = _FlightCoordinator()
    manager = SystemJsonRpcCacheManager(
        SystemCacheManager(store, flight, flight_wait_seconds=2),
        policies,
    )
    leader_loader = _Loader('leader', blocked=True)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    leader_task = asyncio.create_task(
        manager.get_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call, loader=leader_loader)
    )
    await asyncio.wait_for(leader_loader.started.wait(), timeout=1)

    now = datetime.now(UTC)
    try:
        fresh_policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None, digest='2' * 40)
        policies.policy = fresh_policy
        store.entry = CacheEntry(
            key=fresh_policy.key,
            tier=CacheTier.REDIS_TTL,
            payload=b'"fresh"',
            fresh_until=now + timedelta(seconds=1),
            stale_until=now + timedelta(seconds=2),
            sequence=None,
        )
        fresh_loader = _Loader('unused')
        fresh = await manager.get_result_with_usage(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=fresh_loader,
        )
        assert fresh.value == b'"fresh"'
        assert fresh.hit
        assert fresh_loader.calls == 0

        stale_policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None, digest='3' * 40)
        policies.policy = stale_policy
        store.entry = CacheEntry(
            key=stale_policy.key,
            tier=CacheTier.REDIS_TTL,
            payload=b'"stale"',
            fresh_until=now - timedelta(seconds=1),
            stale_until=now + timedelta(seconds=1),
            sequence=None,
        )
        stale_loader = _Loader('unused')
        stale = await manager.get_result_with_usage(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=stale_loader,
        )
        assert stale.value == b'"stale"'
        assert stale.hit
        assert stale_loader.calls == 0

    finally:
        leader_loader.release.set()
        await asyncio.wait_for(leader_task, timeout=1)


async def test_wrong_evm_block_height_is_not_published() -> None:
    store = _Store()
    policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    loader = _Loader({'number': '0x65', 'hash': 'wrong-height'})
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])

    manager = _manager(store, policy, _FlightCoordinator())
    result = await manager.get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
        loader=loader,
    )

    assert result == orjson.dumps({'number': '0x65', 'hash': 'wrong-height'})
    assert store.entry is None


async def test_cancelled_winner_releases_local_and_distributed_flights() -> None:
    store = _Store()
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = _FlightCoordinator()
    manager = _manager(store, policy, flight)
    blocked_loader = _Loader('0x64', blocked=True)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    winner = asyncio.create_task(
        manager.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=blocked_loader,
        )
    )
    await asyncio.wait_for(blocked_loader.started.wait(), timeout=1)
    waiter = asyncio.create_task(
        manager.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=blocked_loader,
        )
    )
    await asyncio.sleep(0)

    winner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await winner
    assert await asyncio.wait_for(waiter, timeout=1) is None
    await asyncio.wait_for(flight.released.wait(), timeout=1)
    assert flight.owner is None

    retry_loader = _Loader('0x65')
    retry = await asyncio.wait_for(
        manager.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=retry_loader,
        ),
        timeout=1,
    )
    assert retry == b'"0x65"'
    assert retry_loader.calls == 1
    await manager.close(drain_seconds=1)


async def test_redis_ttl_response_does_not_wait_for_flight_release() -> None:
    store = _Store()
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = _BlockingReleaseFlight()
    manager = _manager(store, policy, flight)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])

    result = await asyncio.wait_for(
        manager.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=_Loader('0x64'),
        ),
        timeout=0.5,
    )

    assert result == b'"0x64"'
    await asyncio.wait_for(flight.release_started.wait(), timeout=1)
    assert flight.owner is not None

    flight.allow_release.set()
    await asyncio.wait_for(flight.released.wait(), timeout=1)
    await manager.close(drain_seconds=1)


async def test_loader_has_full_budget_after_flight_coordination() -> None:
    store = _Store()
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    manager = SystemJsonRpcCacheManager(
        SystemCacheManager(store, _FlightCoordinator(), flight_wait_seconds=1),
        _PolicyProvider(policy),
    )
    loader = _Loader('0x64', blocked=True)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    task = asyncio.create_task(
        manager.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=loader,
        )
    )

    await asyncio.wait_for(loader.started.wait(), timeout=1)
    await asyncio.sleep(1.1)
    assert not task.done()

    loader.release.set()
    assert await asyncio.wait_for(task, timeout=1) == b'"0x64"'
    assert loader.calls == 1
    await manager.close(drain_seconds=1)


async def test_postgres_retention_response_does_not_wait_for_commit() -> None:
    store = _BlockingCommitStore()
    policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    manager = _manager(store, policy, _FlightCoordinator())
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])

    result = await asyncio.wait_for(
        manager.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=_Loader({'number': '0x64', 'hash': 'payload'}),
        ),
        timeout=0.5,
    )

    assert result == orjson.dumps({'number': '0x64', 'hash': 'payload'})
    await asyncio.wait_for(store.commit_started.wait(), timeout=1)
    await manager.close(drain_seconds=0)
    assert store.commit_cancelled


async def test_postgres_retention_publisher_rejects_item_and_byte_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _BlockingCommitStore()
    publisher = PostgresRetentionPublisher(store)
    flight = _FlightCoordinator()
    policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=b'four',
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )

    async def heartbeat() -> None:
        await asyncio.Event().wait()

    first_heartbeat = asyncio.create_task(heartbeat())
    second_heartbeat = asyncio.create_task(heartbeat())
    lease = CacheFlightLease(token='owner-1', fence=1)
    monkeypatch.setattr('app.services.system_cache.publisher.PUBLISH_MAX_ITEMS', 1)
    assert publisher.submit(
        entry,
        lease,
        refresh=False,
        flight=flight,
        heartbeat=first_heartbeat,
        ownership_lost=asyncio.Event(),
    )
    assert not publisher.submit(
        entry,
        lease,
        refresh=False,
        flight=flight,
        heartbeat=second_heartbeat,
        ownership_lost=asyncio.Event(),
    )
    second_heartbeat.cancel()
    await asyncio.gather(second_heartbeat, return_exceptions=True)
    await publisher.close(drain_seconds=0)

    byte_heartbeat = asyncio.create_task(heartbeat())
    byte_limited = PostgresRetentionPublisher(_Store())
    monkeypatch.setattr('app.services.system_cache.publisher.PUBLISH_MAX_ITEMS', 64)
    monkeypatch.setattr('app.services.system_cache.publisher.PUBLISH_MAX_BYTES', 3)
    assert not byte_limited.submit(
        entry,
        lease,
        refresh=False,
        flight=flight,
        heartbeat=byte_heartbeat,
        ownership_lost=asyncio.Event(),
    )
    byte_heartbeat.cancel()
    await asyncio.gather(byte_heartbeat, return_exceptions=True)


async def test_cache_is_rechecked_after_distributed_flight_acquire() -> None:
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    now = datetime.now(UTC)
    saved = CacheEntry(
        key=policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"winner"',
        fresh_until=now + timedelta(seconds=1),
        stale_until=now + timedelta(seconds=2),
        sequence=None,
    )
    store = _AcquireRaceStore(saved)
    loader = _Loader('loser')
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])

    result = await _manager(store, policy, _FlightCoordinator()).get_result(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        call=call,
        loader=loader,
    )

    assert result == b'"winner"'
    assert loader.calls == 0
    assert store.writes == 0


async def test_redis_ttl_commit_rejects_old_owner(test_redis: Redis) -> None:
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = RedisTtlFlight(test_redis, lease_ms=1000)
    old_lease = await flight.acquire(policy.key)
    assert old_lease is not None
    await test_redis.delete(flight_key(policy.key))
    new_lease = await flight.acquire(policy.key)
    assert new_lease is not None and new_lease.fence > old_lease.fence
    now = datetime.now(UTC)
    old_entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"old"',
        fresh_until=now + timedelta(seconds=1),
        stale_until=now + timedelta(seconds=2),
        sequence=None,
    )
    new_entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"new"',
        fresh_until=now + timedelta(seconds=1),
        stale_until=now + timedelta(seconds=2),
        sequence=None,
    )
    store = RedisTtlStore(test_redis)

    assert await store.commit(new_entry, new_lease, refresh=False)
    assert not await store.commit(old_entry, old_lease, refresh=False)
    saved = await store.get(policy)
    assert saved is not None and saved.payload == b'"new"'


async def test_two_redis_managers_share_one_overlapping_loader(test_redis: Redis) -> None:
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    leader_loader = _Loader('winner', blocked=True)
    follower_loader = _Loader('loser')
    leader = SystemJsonRpcCacheManager(
        SystemCacheManager(
            RedisTtlStore(test_redis),
            RedisTtlFlight(test_redis, lease_ms=1000),
            flight_wait_seconds=2,
        ),
        _PolicyProvider(policy),
    )
    follower = SystemJsonRpcCacheManager(
        SystemCacheManager(
            RedisTtlStore(test_redis),
            RedisTtlFlight(test_redis, lease_ms=1000),
            flight_wait_seconds=2,
        ),
        _PolicyProvider(policy),
    )
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])
    leader_task = asyncio.create_task(
        leader.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=leader_loader,
        )
    )
    await asyncio.wait_for(leader_loader.started.wait(), timeout=1)
    follower_task = asyncio.create_task(
        follower.get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=follower_loader,
        )
    )
    await asyncio.sleep(0.1)
    assert follower_loader.calls == 0
    leader_loader.release.set()

    leader_result, follower_result = await asyncio.wait_for(
        asyncio.gather(leader_task, follower_task),
        timeout=2,
    )
    assert leader_result == follower_result == b'"winner"'
    assert leader_loader.calls == 1
    assert follower_loader.calls == 0


async def test_fence_advances_after_redis_counter_loss(test_redis: Redis) -> None:
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = RedisTtlFlight(test_redis, lease_ms=1000)
    old_lease = await flight.acquire(policy.key)
    assert old_lease is not None
    await flight.release(policy.key, old_lease)
    await test_redis.delete(redis_keys.build_key('system_cache', 'v1', 'fence'))

    new_lease = await flight.acquire(policy.key)

    assert new_lease is not None and new_lease.fence > old_lease.fence


async def test_utxo_hash_string_can_publish() -> None:
    policy = CachePolicy(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=Chain.BITCOIN,
            network=Network.MAINNET,
            operation='getblockhash',
            digest='2' * 40,
        ),
        tier=CacheTier.REDIS_TTL,
        retention_seconds=None,
        ttl_ms=1000,
        sequence=100,
    )
    store = _Store()
    loader = _Loader('a' * 64)
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblockhash', params=[100])

    result = await _manager(store, policy, _FlightCoordinator()).get_result(
        chain=Chain.BITCOIN,
        network=Network.MAINNET,
        call=call,
        loader=loader,
    )

    assert result == orjson.dumps('a' * 64)
    assert store.entry is not None and store.entry.payload == result


async def test_invalid_utxo_hash_result_is_not_published() -> None:
    policy = CachePolicy(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=Chain.BITCOIN,
            network=Network.MAINNET,
            operation='getblockhash',
            digest='3' * 40,
        ),
        tier=CacheTier.REDIS_TTL,
        retention_seconds=None,
        ttl_ms=1000,
        sequence=100,
    )
    store = _Store()
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblockhash', params=[100])

    await _manager(store, policy, _FlightCoordinator()).get_result(
        chain=Chain.BITCOIN,
        network=Network.MAINNET,
        call=call,
        loader=_Loader(100),
    )

    assert store.entry is None


async def test_utxo_block_with_wrong_hash_is_not_published() -> None:
    expected_hash = 'a' * 64
    policy = CachePolicy(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=Chain.BITCOIN,
            network=Network.MAINNET,
            operation='getblock',
            digest='4' * 40,
        ),
        tier=CacheTier.POSTGRES_RETENTION,
        retention_seconds=3600,
        ttl_ms=None,
        sequence=None,
    )
    store = _Store()
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblock', params=[expected_hash, 3])

    await _manager(store, policy, _FlightCoordinator()).get_result(
        chain=Chain.BITCOIN,
        network=Network.MAINNET,
        call=call,
        loader=_Loader({'height': 100, 'hash': 'b' * 64}),
    )

    assert store.entry is None


async def test_utxo_block_can_publish_without_hash_height_mapping() -> None:
    expected_hash = 'a' * 64
    policy = CachePolicy(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=Chain.BITCOIN,
            network=Network.MAINNET,
            operation='getblock',
            digest='5' * 40,
        ),
        tier=CacheTier.POSTGRES_RETENTION,
        retention_seconds=3600,
        ttl_ms=None,
        sequence=None,
    )
    store = _Store()
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblock', params=[expected_hash, 3])

    manager = _manager(store, policy, _FlightCoordinator())
    result = await manager.get_result(
        chain=Chain.BITCOIN,
        network=Network.MAINNET,
        call=call,
        loader=_Loader({'height': 100, 'hash': expected_hash}),
    )
    await manager.close(drain_seconds=1)

    assert result == orjson.dumps({'height': 100, 'hash': expected_hash})
    assert store.entry is not None and store.entry.payload == result


async def test_ownership_loss_cancels_blocked_store_commit() -> None:
    store = _BlockingCommitStore()
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = _LosingFlight()
    loader = _Loader('result')
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])

    result = await asyncio.wait_for(
        _manager(store, policy, flight).get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=loader,
        ),
        timeout=3,
    )

    assert result == b'"result"'
    assert store.commit_started.is_set()
    assert store.commit_cancelled
    assert store.entry is None


async def test_commit_cleanup_is_bounded_when_cancel_is_ignored() -> None:
    store = _IgnoringCancelStore()
    policy = _policy(tier=CacheTier.REDIS_TTL, ttl_ms=1000, sequence=None)
    flight = _LosingFlight()
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[])

    result = await asyncio.wait_for(
        _manager(store, policy, flight).get_result(
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            call=call,
            loader=_Loader('result'),
        ),
        timeout=3,
    )

    assert result == b'"result"'
    assert store.commit_started.is_set()
    assert store.cancel_seen.is_set()
    assert not store.completed.is_set()
    assert flight.owner is None

    store.release.set()
    await asyncio.wait_for(store.completed.wait(), timeout=1)


async def test_postgres_retention_old_owner_rejected_before_new_publish(orm_schema: None) -> None:
    del orm_schema
    policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    flight = PostgresRetentionFlight(lease_ms=1000)
    store = PostgresRetentionStore()
    old_lease = await flight.acquire(policy.key)
    assert old_lease is not None
    assert await flight.renew(policy.key, old_lease)
    commit_started = asyncio.Event()
    commit_gate = asyncio.Event()
    old_entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=b'{"number":"0x64","hash":"old"}',
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )

    async def commit_old() -> bool:
        commit_started.set()
        await commit_gate.wait()
        return await store.commit(old_entry, old_lease, refresh=False)

    old_commit = asyncio.create_task(commit_old())
    await asyncio.wait_for(commit_started.wait(), timeout=1)
    connection = connections.get('default')
    await connection.execute_query(
        """
        UPDATE system_cache_payload_lease
        SET lease_until = clock_timestamp() - INTERVAL '1 millisecond'
        WHERE transport = $1 AND chain = $2 AND network = $3 AND operation = $4 AND cache_key = $5
          AND token = $6 AND fence = $7
        """,
        [
            policy.key.transport.value,
            policy.key.chain.value,
            policy.key.network.value,
            policy.key.operation,
            policy.key.digest,
            old_lease.token,
            old_lease.fence,
        ],
    )
    new_lease = await flight.acquire(policy.key)
    assert new_lease is not None and new_lease.fence > old_lease.fence

    commit_gate.set()
    assert not await asyncio.wait_for(old_commit, timeout=1)
    assert await store.get(policy) is None
    await flight.release(policy.key, new_lease)
    result = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=1, max_bytes=1024)
    assert result.deleted_rows == 0
    assert result.deleted_bytes == 0
    assert not result.has_more


async def test_postgres_retention_commit_survives_client_cancel_after_commit(orm_schema: None) -> None:
    del orm_schema
    policy = _policy(tier=CacheTier.POSTGRES_RETENTION, ttl_ms=None, sequence=100)
    flight = PostgresRetentionFlight(lease_ms=1000)
    store = PostgresRetentionStore()
    lease = await flight.acquire(policy.key)
    assert lease is not None
    entry = CacheEntry(
        key=policy.key,
        tier=CacheTier.POSTGRES_RETENTION,
        payload=b'{"number":"0x64","hash":"committed"}',
        fresh_until=None,
        stale_until=None,
        sequence=100,
    )
    committed = asyncio.Event()

    async def commit_without_ack() -> None:
        assert await store.commit(entry, lease, refresh=False)
        committed.set()
        await asyncio.Event().wait()

    commit_task = asyncio.create_task(commit_without_ack())
    await asyncio.wait_for(committed.wait(), timeout=1)
    commit_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await commit_task

    saved = await store.get(policy)
    assert saved is not None and saved.payload == entry.payload
    await flight.release(policy.key, lease)
