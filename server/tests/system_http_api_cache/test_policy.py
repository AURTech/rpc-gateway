import pytest
from app.model.blockchain import Chain, Network
from app.model.public import PublicHttpApiRequest, TronHttpApiFamily
from app.model.system_cache import CacheTier
from app.model.transport import Transport
from app.services.system_http_api_cache.policy import SystemHttpApiCachePolicy


def _policy() -> SystemHttpApiCachePolicy:
    return SystemHttpApiCachePolicy(
        redis_ttl_ms=250,
        postgres_retention_seconds=dict.fromkeys(Chain, 3600),
    )


def _request(path: str, *, body: bytes = b'', method: str = 'POST', query: tuple[tuple[str, str], ...] = ()):
    return PublicHttpApiRequest(
        method=method,
        path=path,
        family=TronHttpApiFamily.WALLET,
        path_key=None,
        query=query,
        body=body,
    )


def test_getnodeinfo_uses_redis_ttl() -> None:
    classified = _policy().classify(
        chain=Chain.TRON,
        network=Network.MAINNET,
        request=_request('/wallet/getnodeinfo'),
    )

    assert classified is not None
    assert classified.policy.tier is CacheTier.REDIS_TTL
    assert classified.policy.ttl_ms == 250
    assert classified.policy.key.transport is Transport.HTTP_API
    assert classified.policy.key.operation == '/wallet/getnodeinfo'


def test_getblockbynum_uses_postgres_retention() -> None:
    classified = _policy().classify(
        chain=Chain.TRON,
        network=Network.NILE,
        request=_request('/wallet/getblockbynum', body=b'{"visible":true,"num":123}'),
    )

    assert classified is not None
    assert classified.policy.tier is CacheTier.POSTGRES_RETENTION
    assert classified.policy.retention_seconds == 3600
    assert classified.policy.sequence == 123


@pytest.mark.parametrize(
    'case',
    [
        _request('/wallet/getnodeinfo', body=b'{}'),
        _request('/wallet/getnodeinfo', method='GET'),
        _request('/wallet/getnodeinfo', query=(('visible', 'true'),)),
        _request('/walletsolidity/getnodeinfo'),
        _request('/wallet/getblockbynum', body=b'{"num":123}'),
        _request('/wallet/getblockbynum', body=b'{"num":123,"visible":false}'),
        _request('/wallet/getblockbynum', body=b'{"num":-1,"visible":true}'),
        _request('/wallet/getblockbynum', body=b'{"num":true,"visible":true}'),
        _request('/wallet/getblockbynum', body=b'{"num":123,"visible":true,"extra":1}'),
        _request('/wallet/getblockbynum', body=b'not-json'),
    ],
)
def test_policy_rejects_noncanonical_requests(case: PublicHttpApiRequest) -> None:
    assert _policy().classify(chain=Chain.TRON, network=Network.MAINNET, request=case) is None
