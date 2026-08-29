from datetime import UTC, datetime, timedelta

import pytest
from app.model.blockchain import Chain, Network
from app.model.public import JsonRpcCall
from app.model.system_cache import CacheEntry, CacheFlightLease, CacheKey, CachePolicy, CacheTier
from app.model.transport import Transport
from app.services.system_cache import SystemCacheManager
from app.services.system_jsonrpc_cache import SystemJsonRpcCacheManager


class _Store:
    def __init__(self, entry: CacheEntry | None) -> None:
        self._entry = entry

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        del policy
        return self._entry

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        del entry, lease, refresh
        return True


class _Policies:
    def __init__(self, policy: CachePolicy) -> None:
        self._policy = policy

    def classify(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> CachePolicy:
        del chain, network, call
        return self._policy


class _Flight:
    async def acquire(self, key: CacheKey) -> CacheFlightLease | None:
        del key
        return None

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        del key, lease
        return False

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        del key, lease
        return None

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool:
        del key, timeout_seconds
        return False


def _manager(entry: CacheEntry | None, policy: CachePolicy) -> SystemJsonRpcCacheManager:
    core = SystemCacheManager(_Store(entry), _Flight(), flight_wait_seconds=1)
    return SystemJsonRpcCacheManager(
        core,
        _Policies(policy),
    )


@pytest.mark.anyio
async def test_lookup_exposes_cache_eligibility_and_hit() -> None:
    key = CacheKey(
        transport=Transport.JSONRPC,
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        operation='eth_chainId',
        digest='digest',
    )
    policy = CachePolicy(
        key=key,
        tier=CacheTier.REDIS_TTL,
        retention_seconds=None,
        ttl_ms=100,
        sequence=None,
    )
    entry = CacheEntry(
        key=key,
        tier=CacheTier.REDIS_TTL,
        payload=b'"0x1"',
        fresh_until=datetime.now(UTC) + timedelta(seconds=1),
        stale_until=datetime.now(UTC) + timedelta(seconds=2),
        sequence=None,
    )
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_chainId')
    manager = _manager(entry, policy)

    result = await manager.lookup_result_with_usage(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)

    assert result.eligible
    assert result.hit
    assert result.value == b'"0x1"'
    assert await manager.lookup_result(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call) == b'"0x1"'
