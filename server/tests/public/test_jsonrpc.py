from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from app.api.public.jsonrpc import _stream_raw_result
from app.model.account import AccountRole
from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import (
    JsonRpcForwardingFailure,
    JsonRpcForwardingFailureCode,
    JsonRpcForwardingSuccess,
    JsonRpcRoutePlan,
)
from app.model.public import (
    JsonRpcCall,
    JsonRpcCallResult,
    JsonRpcErrorResponse,
    JsonRpcSuccessResponse,
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
)
from app.model.system_jsonrpc_cache import SystemJsonRpcCacheResult
from app.model.transport import Transport
from app.services.admission import AdmissionDecision
from app.services.public.jsonrpc.manager import RPC_CACHE_HIT_HEADER, JsonRpcLoader, PublicJsonRpcManager
from tests.jsonrpc_forwarding.factories import make_endpoint, make_plan


class _Access:
    @staticmethod
    def match_host(host: str | None, transport: Transport) -> PublicGatewayAddress:
        del host
        return PublicGatewayAddress(chain=Chain.ETHEREUM, network=Network.MAINNET, transport=transport)

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
    @staticmethod
    @asynccontextmanager
    async def acquire_inflight() -> AsyncGenerator[AdmissionDecision]:
        yield AdmissionDecision(limited=False, enforced=False)

    @staticmethod
    async def acquire_pre_auth(client_ip: str) -> AdmissionDecision:
        del client_ip
        return AdmissionDecision(limited=False, enforced=False)

    @staticmethod
    async def acquire_post_auth(account_id: str, app_id: str) -> AdmissionDecision:
        del account_id, app_id
        return AdmissionDecision(limited=False, enforced=False)


class _LimitedAdmission(_Admission):
    @staticmethod
    @asynccontextmanager
    async def acquire_inflight() -> AsyncGenerator[AdmissionDecision]:
        yield AdmissionDecision(limited=True, enforced=True, retry_after_ms=1000)


class _RejectedAccess(_Access):
    @staticmethod
    async def authenticate(path_key: str | None, authorization: str | None) -> PublicGatewayIdentity:
        del path_key, authorization
        raise AssertionError('A concurrency-limited request must not authenticate.')


class _Forwarding:
    @staticmethod
    async def load_plan(
        *, account_id: str, gateway_id: str, chain: Chain, network: Network, method: str
    ) -> JsonRpcForwardingFailure:
        del account_id, gateway_id, chain, network, method
        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)

    @staticmethod
    async def forward(plan: JsonRpcRoutePlan, call: JsonRpcCall) -> JsonRpcForwardingFailure:
        del plan, call
        return JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)


class _SuccessfulForwarding:
    @staticmethod
    async def load_plan(*, account_id: str, gateway_id: str, chain: Chain, network: Network, method: str) -> JsonRpcRoutePlan:
        del account_id, gateway_id, chain, network, method
        return make_plan([make_endpoint('endpoint-1')])

    @staticmethod
    async def forward(plan: JsonRpcRoutePlan, call: JsonRpcCall) -> JsonRpcForwardingSuccess:
        del plan
        response = JsonRpcSuccessResponse(id=call.request_id(), result=b'{ "value": 1e2 }')
        return JsonRpcForwardingSuccess(response=response)


class _SystemCache:
    def __init__(self, result: SystemJsonRpcCacheResult) -> None:
        self._result = result

    async def get_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
        loader: JsonRpcLoader,
    ) -> SystemJsonRpcCacheResult:
        del chain, network, call, loader
        return self._result

    async def lookup_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
    ) -> SystemJsonRpcCacheResult:
        del chain, network, call
        return self._result


async def _call(cache_result: SystemJsonRpcCacheResult) -> JsonRpcCallResult:
    manager = PublicJsonRpcManager(_Access(), _Admission(), _Forwarding(), _SystemCache(cache_result))
    return await manager.call(
        host='ether-jsonrpc.example.test',
        body=b'{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber"}',
        path_key='key',
        authorization=None,
        client_ip='127.0.0.1',
    )


@pytest.mark.anyio
async def test_cache_hit_adds_response_header() -> None:
    result = await _call(SystemJsonRpcCacheResult(value=b'"0x123"', eligible=True, hit=True))

    assert result.headers == {RPC_CACHE_HIT_HEADER: 'HIT'}
    assert result.raw_result == b'"0x123"'


@pytest.mark.anyio
async def test_cache_miss_does_not_add_response_header() -> None:
    result = await _call(SystemJsonRpcCacheResult(value=None, eligible=True, hit=False))

    assert RPC_CACHE_HIT_HEADER not in result.headers


@pytest.mark.anyio
async def test_forwarded_success_uses_raw_result_response() -> None:
    manager = PublicJsonRpcManager(_Access(), _Admission(), _SuccessfulForwarding())

    result = await manager.call(
        host='ether-jsonrpc.example.test',
        body=b'{"jsonrpc":"2.0","id":1,"method":"eth_getBlockByNumber","params":["latest",false]}',
        path_key='key',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert result.response is None
    assert result.raw_result == b'{ "value": 1e2 }'
    assert result.request_id == 1


def test_raw_result_response_bytes_match_streamed_envelope() -> None:
    result = JsonRpcCallResult(
        response=None,
        status_code=200,
        raw_result=b'{ "value": 1e2 }',
        request_id='request',
    )

    response_bytes = PublicJsonRpcManager._response_bytes(result)

    assert response_bytes == len(b'{"jsonrpc":"2.0","id":"request","result":{ "value": 1e2 }}')


@pytest.mark.anyio
async def test_raw_result_stream_preserves_huge_integer_id() -> None:
    request_id = 10**100

    content = b''.join([chunk async for chunk in _stream_raw_result(request_id, b'null')])

    assert content == f'{{"jsonrpc":"2.0","id":{request_id},"result":null}}'.encode()


@pytest.mark.anyio
async def test_inflight_limit_rejects_before_authentication_and_cache() -> None:
    manager = PublicJsonRpcManager(
        _RejectedAccess(),
        _LimitedAdmission(),
        _Forwarding(),
        _SystemCache(SystemJsonRpcCacheResult(value=b'"unused"', eligible=True, hit=True)),
    )

    result = await manager.call(
        host='ether-jsonrpc.example.test',
        body=b'{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber"}',
        path_key='key',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert result.status_code == 200
    assert isinstance(result.response, JsonRpcErrorResponse)
    assert result.response.error.code == -32029
    assert result.headers['Retry-After'] == '1'
