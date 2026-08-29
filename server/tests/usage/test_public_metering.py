import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from app.model.account import AccountRole
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointHttpApiRequest
from app.model.http_api_forwarding import HttpApiForwardingFailure, HttpApiForwardingFailureCode, HttpApiRoutePlan
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.model.jsonrpc_forwarding import JsonRpcForwardingFailure, JsonRpcForwardingFailureCode, JsonRpcRoutePlan
from app.model.public import (
    JsonRpcCall,
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
)
from app.model.transport import Transport
from app.model.usage import GatewayUsageEvent
from app.services.admission import AdmissionDecision
from app.services.public import PublicHttpApiManager, PublicJsonRpcManager
from tests.jsonrpc_forwarding.factories import make_endpoint, make_plan


class _Access:
    @staticmethod
    def match_host(host: str | None, transport: Transport) -> PublicGatewayAddress:
        del host
        return PublicGatewayAddress(chain=Chain.TRON, network=Network.MAINNET, transport=transport)

    @staticmethod
    async def authenticate(path_key: str | None, authorization: str | None) -> PublicGatewayIdentity:
        del path_key, authorization
        return PublicGatewayIdentity(account_id='account-1', account_role=AccountRole.USER, app_id='app-1')

    @staticmethod
    async def get_context(
        address: PublicGatewayAddress,
        identity: PublicGatewayIdentity,
    ) -> PublicGatewayContext:
        del identity
        return PublicGatewayContext(
            account_id='account-1',
            account_role=AccountRole.USER,
            app_id='app-1',
            gateway_id='gateway-1',
            chain=address.chain,
            network=address.network,
            transport=address.transport,
        )


class _Admission:
    def __init__(self, *, post_auth_limited: bool = False) -> None:
        self._post_auth_limited = post_auth_limited

    @asynccontextmanager
    async def acquire_inflight(self) -> AsyncGenerator[AdmissionDecision]:
        yield AdmissionDecision(limited=False, enforced=False)

    @staticmethod
    async def acquire_pre_auth(client_ip: str) -> AdmissionDecision:
        del client_ip
        return AdmissionDecision(limited=False, enforced=False)

    async def acquire_post_auth(self, account_id: str, app_id: str) -> AdmissionDecision:
        del account_id, app_id
        return AdmissionDecision(limited=self._post_auth_limited, enforced=self._post_auth_limited)


class _JsonRpcForwarding:
    @staticmethod
    async def load_plan(
        *, account_id: str, gateway_id: str, chain: Chain, network: Network, method: str
    ) -> JsonRpcRoutePlan | JsonRpcForwardingFailure:
        del account_id, gateway_id, chain, network, method
        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)

    @staticmethod
    async def forward(plan: JsonRpcRoutePlan, call: JsonRpcCall) -> JsonRpcForwardingFailure:
        del plan, call
        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)


class _AttemptingJsonRpcForwarding(_JsonRpcForwarding):
    plan = make_plan([make_endpoint('endpoint-1'), make_endpoint('endpoint-2')])

    @staticmethod
    async def load_plan(*, account_id: str, gateway_id: str, chain: Chain, network: Network, method: str) -> JsonRpcRoutePlan:
        del account_id, gateway_id, chain, network, method
        return _AttemptingJsonRpcForwarding.plan

    @staticmethod
    async def forward(plan: JsonRpcRoutePlan, call: JsonRpcCall) -> JsonRpcForwardingFailure:
        del plan, call
        return JsonRpcForwardingFailure(
            code=JsonRpcForwardingFailureCode.ATTEMPTS_FAILED,
            attempted_endpoint_ids=('endpoint-1', 'endpoint-2'),
        )


class _HttpForwarding:
    @staticmethod
    async def load_plan(
        *, account_id: str, gateway_id: str, chain: Chain, network: Network
    ) -> HttpApiRoutePlan | HttpApiForwardingFailure:
        del account_id, gateway_id, chain, network
        return HttpApiForwardingFailure(code=HttpApiForwardingFailureCode.NO_ENDPOINT)

    @staticmethod
    async def forward(plan: HttpApiRoutePlan, request: EndpointHttpApiRequest) -> HttpApiForwardingFailure:
        del plan, request
        return HttpApiForwardingFailure(code=HttpApiForwardingFailureCode.NO_ENDPOINT)


class _EmptyHttpRouteForwarding(_HttpForwarding):
    plan = HttpApiRoutePlan(
        id='route-1',
        account_id='account-1',
        gateway_id='gateway-1',
        chain=Chain.TRON,
        network=Network.MAINNET,
        strategy_type=HttpApiRoutingStrategyType.LOAD_BALANCE,
        max_attempts=3,
        retry_policy=HttpApiRetryPolicy.SAFE_ONLY,
        targets=(),
    )

    @staticmethod
    async def load_plan(*, account_id: str, gateway_id: str, chain: Chain, network: Network) -> HttpApiRoutePlan:
        del account_id, gateway_id, chain, network
        return _EmptyHttpRouteForwarding.plan


class _Usage:
    def __init__(self) -> None:
        self.events: list[GatewayUsageEvent] = []

    def submit(self, event: GatewayUsageEvent) -> bool:
        self.events.append(event)
        return True


class _CancelledJsonRpcForwarding(_JsonRpcForwarding):
    @staticmethod
    async def load_plan(
        *, account_id: str, gateway_id: str, chain: Chain, network: Network, method: str
    ) -> JsonRpcForwardingFailure:
        del account_id, gateway_id, chain, network, method
        raise asyncio.CancelledError


class _CancelledHttpForwarding(_HttpForwarding):
    @staticmethod
    async def load_plan(*, account_id: str, gateway_id: str, chain: Chain, network: Network) -> HttpApiForwardingFailure:
        del account_id, gateway_id, chain, network
        raise asyncio.CancelledError


@pytest.mark.anyio
async def test_jsonrpc_records_gateway_failure_after_context() -> None:
    usage = _Usage()
    manager = PublicJsonRpcManager(_Access(), _Admission(), _JsonRpcForwarding(), usage=usage)

    result = await manager.call(
        host='tron-mainnet.example.test',
        body=b'{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber"}',
        path_key='key',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert result.status_code == 200
    assert len(usage.events) == 1
    assert usage.events[0].gateway_id == 'gateway-1'
    assert usage.events[0].chain is Chain.TRON
    assert usage.events[0].network is Network.MAINNET
    assert usage.events[0].method == 'eth_blockNumber'
    assert not usage.events[0].successful


@pytest.mark.anyio
async def test_jsonrpc_records_route_endpoint_attempts() -> None:
    usage = _Usage()
    manager = PublicJsonRpcManager(_Access(), _Admission(), _AttemptingJsonRpcForwarding(), usage=usage)

    await manager.call(
        host='tron-mainnet.example.test',
        body=b'{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber"}',
        path_key='key',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert len(usage.events) == 1
    assert usage.events[0].route_id == _AttemptingJsonRpcForwarding.plan.id
    assert usage.events[0].attempted_endpoint_ids == ('endpoint-1', 'endpoint-2')


@pytest.mark.anyio
async def test_post_auth_limit_is_not_metered() -> None:
    usage = _Usage()
    manager = PublicJsonRpcManager(_Access(), _Admission(post_auth_limited=True), _JsonRpcForwarding(), usage=usage)

    await manager.call(
        host='tron-mainnet.example.test',
        body=b'{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber"}',
        path_key='key',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert usage.events == []


@pytest.mark.anyio
async def test_http_api_records_normalized_operation() -> None:
    usage = _Usage()
    manager = PublicHttpApiManager(_Access(), _Admission(), _HttpForwarding(), usage)

    result = await manager.call(
        host='tron-mainnet.example.test',
        method='GET',
        raw_path='key/v1/accounts/TAddress/transactions',
        headers=[],
        query=[('only_confirmed', 'true')],
        body=b'',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert result.status_code == 503
    assert len(usage.events) == 1
    assert usage.events[0].method == 'GET /v1/accounts/{id}/transactions'
    assert 'TAddress' not in usage.events[0].method


@pytest.mark.anyio
async def test_http_api_records_empty_route_failure_without_attempts() -> None:
    usage = _Usage()
    manager = PublicHttpApiManager(_Access(), _Admission(), _EmptyHttpRouteForwarding(), usage)

    result = await manager.call(
        host='tron-mainnet.example.test',
        method='POST',
        raw_path='key/wallet/getnowblock',
        headers=[],
        query=[],
        body=b'{}',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert result.status_code == 503
    assert len(usage.events) == 1
    assert usage.events[0].route_id == _EmptyHttpRouteForwarding.plan.id
    assert usage.events[0].attempted_endpoint_ids == ()
    assert not usage.events[0].successful


@pytest.mark.anyio
async def test_jsonrpc_cancellation_is_not_metered() -> None:
    usage = _Usage()
    manager = PublicJsonRpcManager(_Access(), _Admission(), _CancelledJsonRpcForwarding(), usage=usage)

    with pytest.raises(asyncio.CancelledError):
        await manager.call(
            host='tron-mainnet.example.test',
            body=b'{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber"}',
            path_key='key',
            authorization=None,
            client_ip='127.0.0.1',
        )

    assert usage.events == []


@pytest.mark.anyio
async def test_http_api_cancellation_is_not_metered() -> None:
    usage = _Usage()
    manager = PublicHttpApiManager(_Access(), _Admission(), _CancelledHttpForwarding(), usage)

    with pytest.raises(asyncio.CancelledError):
        await manager.call(
            host='tron-mainnet.example.test',
            method='GET',
            raw_path='key/v1/accounts/TAddress/transactions',
            headers=[],
            query=[],
            body=b'',
            authorization=None,
            client_ip='127.0.0.1',
        )

    assert usage.events == []
