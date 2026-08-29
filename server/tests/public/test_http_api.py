from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import orjson
import pytest
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointHttpApiRequest
from app.model.http_api_forwarding import HttpApiForwardingFailure, HttpApiRoutePlan
from app.model.public import (
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
    PublicHttpApiRequest,
    PublicHttpApiResult,
    TronHttpApiFamily,
)
from app.model.transport import Transport
from app.services.admission import AdmissionDecision
from app.services.public.http_api import PublicHttpApiManager, TronHttpApiAdapter


class _RejectedAccess:
    @staticmethod
    def match_host(host: str | None, transport: Transport) -> PublicGatewayAddress:
        del host
        return PublicGatewayAddress(chain=Chain.TRON, network=Network.MAINNET, transport=transport)

    @staticmethod
    async def authenticate(path_key: str | None, authorization: str | None) -> PublicGatewayIdentity:
        del path_key, authorization
        raise AssertionError('A concurrency-limited request must not authenticate.')

    @staticmethod
    async def get_context(
        address: PublicGatewayAddress,
        identity: PublicGatewayIdentity,
    ) -> PublicGatewayContext:
        del address, identity
        raise AssertionError('A concurrency-limited request must not load gateway context.')


class _LimitedAdmission:
    @staticmethod
    @asynccontextmanager
    async def acquire_inflight() -> AsyncGenerator[AdmissionDecision]:
        yield AdmissionDecision(limited=True, enforced=True, retry_after_ms=1000)

    @staticmethod
    async def acquire_pre_auth(client_ip: str) -> AdmissionDecision:
        del client_ip
        raise AssertionError('A concurrency-limited request must not enter request-per-second admission.')

    @staticmethod
    async def acquire_post_auth(account_id: str, app_id: str) -> AdmissionDecision:
        del account_id, app_id
        raise AssertionError('A concurrency-limited request must not enter authenticated admission.')


class _UnusedForwarding:
    @staticmethod
    async def load_plan(
        *, account_id: str, gateway_id: str, chain: Chain, network: Network
    ) -> HttpApiRoutePlan | HttpApiForwardingFailure:
        del account_id, gateway_id, chain, network
        raise AssertionError('A concurrency-limited request must not load a forwarding plan.')

    @staticmethod
    async def forward(
        plan: HttpApiRoutePlan,
        request: EndpointHttpApiRequest,
    ) -> HttpApiForwardingFailure:
        del plan, request
        raise AssertionError('A concurrency-limited request must not access an endpoint.')


def test_tron_adapter_parses_path_key_and_preserves_query_order() -> None:
    result = TronHttpApiAdapter.parse(
        'POST',
        'secret/wallet/getnowblock',
        headers=[('Authorization', 'Bearer secret'), ('Content-Type', 'application/json'), ('Cookie', 'private')],
        query=[('value', '1'), ('value', '2')],
        body=b'{}',
    )

    assert isinstance(result, PublicHttpApiRequest)
    assert result.path_key == 'secret'
    assert result.path == '/wallet/getnowblock'
    assert result.query == (('value', '1'), ('value', '2'))
    assert result.headers == {'Content-Type': 'application/json'}
    assert result.body == b'{}'


def test_tron_adapter_supports_bearer_path_families() -> None:
    wallet = TronHttpApiAdapter.parse('GET', 'walletsolidity/getnowblock', headers=[], query=[], body=b'')
    v1 = TronHttpApiAdapter.parse('GET', 'v1/accounts/address', headers=[], query=[], body=b'')

    assert isinstance(wallet, PublicHttpApiRequest)
    assert wallet.path_key is None
    assert wallet.family is TronHttpApiFamily.WALLET
    assert isinstance(v1, PublicHttpApiRequest)
    assert v1.family is TronHttpApiFamily.V1


def test_tron_adapter_uses_official_error_shapes() -> None:
    wallet = TronHttpApiAdapter.error(TronHttpApiFamily.WALLET, 429, 'Rate limit exceeded.')
    v1 = TronHttpApiAdapter.error(TronHttpApiFamily.V1, 429, 'Rate limit exceeded.')

    assert orjson.loads(wallet.body) == {'Error': 'Rate limit exceeded.'}
    assert orjson.loads(v1.body) == {'Success': False, 'Error': 'Rate limit exceeded.', 'StatusCode': 429}
    assert ('Retry-After', '1') in wallet.headers


def test_tron_adapter_rejects_unknown_paths_and_methods() -> None:
    missing = TronHttpApiAdapter.parse('POST', 'walletpbft/getnowblock', headers=[], query=[], body=b'')
    method = TronHttpApiAdapter.parse('DELETE', 'v1/accounts/address', headers=[], query=[], body=b'')

    assert isinstance(missing, PublicHttpApiResult)
    assert missing.status_code == 404
    assert isinstance(method, PublicHttpApiResult)
    assert method.status_code == 405


@pytest.mark.anyio
async def test_inflight_limit_rejects_before_authentication_and_forwarding() -> None:
    manager = PublicHttpApiManager(_RejectedAccess(), _LimitedAdmission(), _UnusedForwarding())

    result = await manager.call(
        host='tron-http-api.example.test',
        method='POST',
        raw_path='wallet/getnowblock',
        headers=[],
        query=[],
        body=b'{}',
        authorization=None,
        client_ip='127.0.0.1',
    )

    assert result.status_code == 429
    assert orjson.loads(result.body) == {'Error': 'Rate limit exceeded.'}
    assert ('Retry-After', '1') in result.headers
