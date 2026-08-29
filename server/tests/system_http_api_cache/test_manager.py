from dataclasses import dataclass

import pytest
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointResponse
from app.model.http_api_forwarding import HttpApiForwardingSuccess
from app.model.public import PublicHttpApiRequest, TronHttpApiFamily
from app.model.system_cache import CacheEntry, CacheFlightLease, CacheKey, CachePolicy
from app.services.system_cache import SystemCacheManager
from app.services.system_http_api_cache import SystemHttpApiCacheManager
from app.services.system_http_api_cache.policy import SystemHttpApiCachePolicy


class _Store:
    def __init__(self) -> None:
        self.entries: dict[CacheKey, CacheEntry] = {}

    async def get(self, policy: CachePolicy) -> CacheEntry | None:
        return self.entries.get(policy.key)

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool:
        del refresh
        self.entries[entry.key] = entry
        return True


class _Flight:
    async def acquire(self, key: CacheKey) -> CacheFlightLease:
        del key
        return CacheFlightLease(token='owner', fence=1)

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool:
        del key, lease
        return True

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None:
        del key, lease

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool:
        del key, timeout_seconds
        return True


@dataclass(slots=True, kw_only=True)
class _Loader:
    body: bytes
    calls: int = 0

    async def load(self) -> HttpApiForwardingSuccess:
        self.calls += 1
        return HttpApiForwardingSuccess(
            response=EndpointResponse(
                status_code=200,
                headers=(('Content-Type', 'application/json'),),
                body=self.body,
                request_bytes=0,
                response_bytes=len(self.body),
            )
        )


def _request(path: str, body: bytes = b'') -> PublicHttpApiRequest:
    return PublicHttpApiRequest(
        method='POST',
        path=path,
        family=TronHttpApiFamily.WALLET,
        path_key=None,
        body=body,
    )


def _manager(store: _Store) -> tuple[SystemCacheManager, SystemHttpApiCacheManager]:
    core = SystemCacheManager(store, _Flight(), flight_wait_seconds=1)
    policies = SystemHttpApiCachePolicy(
        redis_ttl_ms=250,
        postgres_retention_seconds=dict.fromkeys(Chain, 3600),
    )
    return core, SystemHttpApiCacheManager(core, policies)


@pytest.mark.anyio
async def test_valid_node_info_is_published_and_reused() -> None:
    store = _Store()
    core, manager = _manager(store)
    request = _request('/wallet/getnodeinfo')
    loader = _Loader(body=b'{"solidityBlock":"Num:123,ID:abc"}')

    first = await manager.get_result_with_usage(
        chain=Chain.TRON,
        network=Network.MAINNET,
        request=request,
        loader=loader,
    )
    second = await manager.lookup_result_with_usage(
        chain=Chain.TRON,
        network=Network.MAINNET,
        request=request,
    )
    await core.close(drain_seconds=1)

    assert first.eligible and not first.hit
    assert second.hit
    assert loader.calls == 1
    assert len(store.entries) == 1


@pytest.mark.anyio
async def test_invalid_node_info_is_not_published() -> None:
    store = _Store()
    core, manager = _manager(store)
    loader = _Loader(body=b'{"solidityBlock":"invalid"}')

    result = await manager.get_result_with_usage(
        chain=Chain.TRON,
        network=Network.MAINNET,
        request=_request('/wallet/getnodeinfo'),
        loader=loader,
    )
    await core.close(drain_seconds=1)

    assert result.value is not None
    assert not result.hit
    assert store.entries == {}


@pytest.mark.anyio
async def test_block_height_mismatch_is_not_published() -> None:
    store = _Store()
    core, manager = _manager(store)
    request = _request('/wallet/getblockbynum', b'{"num":123,"visible":true}')
    loader = _Loader(body=b'{"block_header":{"raw_data":{"number":122}}}')

    result = await manager.get_result_with_usage(
        chain=Chain.TRON,
        network=Network.NILE,
        request=request,
        loader=loader,
    )
    await core.close(drain_seconds=1)

    assert result.value is not None
    assert store.entries == {}
