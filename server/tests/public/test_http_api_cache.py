from contextlib import asynccontextmanager

import pytest
from app.model.account import AccountRole
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointProtocol, EndpointResponse
from app.model.http_api_forwarding import HttpApiForwardingSuccess, HttpApiRoutePlan, HttpApiRouteTarget
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.model.public import (
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
)
from app.model.system_http_api_cache import SystemHttpApiCacheResult
from app.model.transport import Transport
from app.services.admission import AdmissionDecision
from app.services.public.http_api.manager import HTTP_API_CACHE_HIT_HEADER, PublicHttpApiManager


class _Access:
    def __init__(self, role: AccountRole) -> None:
        self._role = role

    def match_host(self, host: str | None, transport: Transport) -> PublicGatewayAddress | None:
        del host, transport
        return PublicGatewayAddress(chain=Chain.TRON, network=Network.MAINNET, transport=Transport.HTTP_API)

    async def authenticate(self, path_key: str | None, authorization: str | None) -> PublicGatewayIdentity:
        del path_key, authorization
        return PublicGatewayIdentity(account_id='account-1', account_role=self._role, app_id='app-1')

    async def get_context(
        self,
        address: PublicGatewayAddress,
        identity: PublicGatewayIdentity,
    ) -> PublicGatewayContext:
        return PublicGatewayContext(
            account_id=identity.account_id,
            account_role=identity.account_role,
            app_id=identity.app_id,
            gateway_id='gateway-1',
            chain=address.chain,
            network=address.network,
            transport=address.transport,
        )


class _Admission:
    @asynccontextmanager
    async def acquire_inflight(self):
        yield AdmissionDecision(limited=False, enforced=False)

    async def acquire_pre_auth(self, client_ip: str) -> AdmissionDecision:
        del client_ip
        return AdmissionDecision(limited=False, enforced=False)

    async def acquire_post_auth(self, account_id: str, app_id: str) -> AdmissionDecision:
        del account_id, app_id
        return AdmissionDecision(limited=False, enforced=False)


class _Forwarding:
    def __init__(self) -> None:
        self.calls = 0

    async def load_plan(self, *, account_id: str, gateway_id: str, chain: Chain, network: Network) -> HttpApiRoutePlan:
        del account_id, gateway_id
        endpoint = EndpointDescriptor(
            id='endpoint-1',
            account_id='account-1',
            chain=chain,
            network=network,
            protocol=EndpointProtocol.HTTP_API,
            enabled=True,
            version=1,
        )
        return HttpApiRoutePlan(
            id='route-1',
            account_id='account-1',
            gateway_id='gateway-1',
            chain=chain,
            network=network,
            strategy_type=HttpApiRoutingStrategyType.PRIORITY_FAILOVER,
            max_attempts=1,
            retry_policy=HttpApiRetryPolicy.SAFE_ONLY,
            targets=(HttpApiRouteTarget(endpoint=endpoint, position=0, weight=None),),
        )

    async def forward(self, plan: HttpApiRoutePlan, request) -> HttpApiForwardingSuccess:
        del plan, request
        self.calls += 1
        body = b'{"solidityBlock":"Num:123,ID:abc"}'
        return HttpApiForwardingSuccess(
            response=EndpointResponse(
                status_code=200,
                headers=(('Content-Type', 'application/json'),),
                body=body,
                request_bytes=0,
                response_bytes=len(body),
            )
        )


class _Cache:
    def __init__(self, *, hit: bool) -> None:
        self._hit = hit
        self.get_calls = 0
        self.lookup_calls = 0

    async def get_result_with_usage(self, *, chain, network, request, loader):
        del chain, network, request
        self.get_calls += 1
        if self._hit:
            return SystemHttpApiCacheResult(value=await loader.load(), eligible=True, hit=True)
        return SystemHttpApiCacheResult(value=await loader.load(), eligible=True, hit=False)

    async def lookup_result_with_usage(self, *, chain, network, request):
        del chain, network, request
        self.lookup_calls += 1
        if not self._hit:
            return SystemHttpApiCacheResult(value=None, eligible=True, hit=False)
        body = b'{"solidityBlock":"Num:123,ID:abc"}'
        response = EndpointResponse(
            status_code=200,
            headers=(('Content-Type', 'application/json'),),
            body=body,
            request_bytes=0,
            response_bytes=len(body),
        )
        return SystemHttpApiCacheResult(value=HttpApiForwardingSuccess(response=response), eligible=True, hit=True)


async def _call(role: AccountRole, cache: _Cache, forwarding: _Forwarding):
    manager = PublicHttpApiManager(_Access(role), _Admission(), forwarding, system_cache=cache)
    return await manager.call(
        host='tron-httpapi.example.test',
        method='POST',
        raw_path='wallet/getnodeinfo',
        headers=[('Accept', 'application/json')],
        query=[],
        body=b'',
        authorization='Bearer key',
        client_ip='127.0.0.1',
    )


@pytest.mark.anyio
async def test_user_cache_hit_bypasses_forwarding() -> None:
    cache = _Cache(hit=True)
    forwarding = _Forwarding()

    result = await _call(AccountRole.USER, cache, forwarding)

    assert result.status_code == 200
    assert (HTTP_API_CACHE_HIT_HEADER, 'HIT') in result.headers
    assert cache.lookup_calls == 1
    assert cache.get_calls == 0
    assert forwarding.calls == 0


@pytest.mark.anyio
async def test_admin_cache_miss_uses_bound_loader_once() -> None:
    cache = _Cache(hit=False)
    forwarding = _Forwarding()

    result = await _call(AccountRole.ADMIN, cache, forwarding)

    assert result.status_code == 200
    assert (HTTP_API_CACHE_HIT_HEADER, 'HIT') not in result.headers
    assert cache.get_calls == 1
    assert forwarding.calls == 1
