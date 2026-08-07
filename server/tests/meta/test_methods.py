import pytest
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


def _protocol(data: dict, protocol: str) -> dict:
    return next(item for item in data['items'] if item['protocol'] == protocol)


def _method(protocol: dict, value: str) -> dict:
    return next(item for item in protocol['methods'] if item['value'] == value)


@pytest.mark.anyio
async def test_jsonrpc_methods_returns_protocol_catalog(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')

    response = await client.get('/v2/meta/jsonrpc-methods')

    data = assert_ok_response(response)['data']
    assert [item['protocol'] for item in data['items']] == ['evm', 'svm', 'utxo', 'tron']

    evm = _protocol(data, 'evm')
    assert evm['protocol_label'] == 'EVM'
    assert {'label': 'Ethereum Execution APIs', 'url': 'https://ethereum.github.io/execution-apis/'} in evm['sources']
    assert _method(evm, 'eth_call') == {
        'value': 'eth_call',
        'label': 'eth_call',
        'namespace': 'eth',
        'namespace_label': 'ETH',
        'risk': 'read',
        'risk_label': 'Read',
        'deprecated': False,
    }
    assert _method(evm, 'debug_traceCall')['risk'] == 'sensitive'
    assert _method(evm, 'engine_newPayloadV4')['risk'] == 'sensitive'
    assert _method(evm, 'eth_sendRawTransaction')['risk'] == 'write'

    svm = _protocol(data, 'svm')
    assert _method(svm, 'sendTransaction')['risk'] == 'write'
    assert _method(svm, 'getConfirmedBlock')['deprecated'] is True

    utxo = _protocol(data, 'utxo')
    assert _method(utxo, 'getblockchaininfo')['namespace'] == 'blockchain'
    assert _method(utxo, 'sendrawtransaction')['risk'] == 'write'
    assert _method(utxo, 'createwallet')['risk'] == 'sensitive'

    tron = _protocol(data, 'tron')
    assert _method(tron, 'web3_clientVersion')['namespace'] == 'web3'
    assert _method(tron, 'eth_sendRawTransaction')['risk'] == 'write'


@pytest.mark.anyio
async def test_jsonrpc_methods_filters_by_protocol(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')

    response = await client.get('/v2/meta/jsonrpc-methods', params={'protocol': 'svm'})

    data = assert_ok_response(response)['data']
    assert [item['protocol'] for item in data['items']] == ['svm']
    assert _method(data['items'][0], 'getSlot')['risk'] == 'read'


@pytest.mark.anyio
async def test_jsonrpc_methods_requires_authentication(client: AsyncClient) -> None:
    response = await client.get('/v2/meta/jsonrpc-methods')

    assert response.status_code == 401, response.text
