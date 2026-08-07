import orjson
from app.model.public import PublicHttpApiRequest, PublicHttpApiResult, TronHttpApiFamily
from app.services.public.http_api import TronHttpApiAdapter


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
