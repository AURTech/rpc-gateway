import orjson
import pytest
from scripts.gateway_flow_integration import mock_endpoint
from scripts.gateway_flow_integration.solana_fixture import (
    SOLANA_BLOCK_MAX_BYTES,
    SOLANA_BLOCK_MIN_BYTES,
    SOLANA_REFERENCE_BLOCK_TIME,
    SOLANA_REFERENCE_SLOT,
    build_solana_block,
)
from tests.helpers import asgi_client

app = mock_endpoint.app
_BASE58_CHARS = frozenset('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')


def test_realistic_solana_block_matches_mainnet_shape_and_size() -> None:
    block = build_solana_block(437_297_990, 'jsonParsed')
    payload = {'jsonrpc': '2.0', 'id': 1, 'result': block}
    encoded = orjson.dumps(payload)

    assert SOLANA_BLOCK_MIN_BYTES <= len(encoded) <= SOLANA_BLOCK_MAX_BYTES
    assert set(block) == {
        'blockHeight',
        'blockTime',
        'blockhash',
        'parentSlot',
        'previousBlockhash',
        'transactions',
    }
    transactions = block['transactions']
    assert isinstance(transactions, list)
    assert 1_000 <= len(transactions) <= 3_000

    first = transactions[0]
    assert isinstance(first, dict)
    assert set(first) == {'meta', 'transaction', 'version'}
    transaction = first['transaction']
    assert isinstance(transaction, dict)
    message = transaction['message']
    assert isinstance(message, dict)
    account_keys = message['accountKeys']
    assert isinstance(account_keys, list)
    assert isinstance(account_keys[0], dict)
    signatures = transaction['signatures']
    assert isinstance(signatures, list)
    signature = signatures[0]
    assert isinstance(signature, str)
    assert len(signature) == 88
    assert set(signature) <= _BASE58_CHARS


def test_realistic_solana_block_supports_compiled_json_encoding() -> None:
    block = build_solana_block(437_297_990, 'json')
    payload = {'jsonrpc': '2.0', 'id': 1, 'result': block}
    assert SOLANA_BLOCK_MIN_BYTES <= len(orjson.dumps(payload)) <= SOLANA_BLOCK_MAX_BYTES
    transactions = block['transactions']
    assert isinstance(transactions, list)
    first = transactions[0]
    assert isinstance(first, dict)
    transaction = first['transaction']
    assert isinstance(transaction, dict)
    message = transaction['message']
    assert isinstance(message, dict)
    assert set(message) == {'accountKeys', 'addressTableLookups', 'header', 'instructions', 'recentBlockhash'}
    account_keys = message['accountKeys']
    assert isinstance(account_keys, list)
    assert isinstance(account_keys[0], str)


def test_realistic_solana_blocks_reuse_transaction_fixture() -> None:
    first = build_solana_block(437_297_990, 'jsonParsed')
    second = build_solana_block(437_297_991, 'jsonParsed')

    assert first['transactions'] is second['transactions']
    assert first['blockhash'] != second['blockhash']
    assert first['parentSlot'] == 437_297_989
    assert second['parentSlot'] == 437_297_990


@pytest.mark.anyio
async def test_mock_exposes_realistic_solana_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('INTEGRATION_RUN_TOKEN', 'test-token')
    request = {
        'jsonrpc': '2.0',
        'id': 17,
        'method': 'getBlock',
        'params': [437_297_990, {'encoding': 'jsonParsed', 'commitment': 'finalized', 'rewards': False}],
    }
    async with asgi_client(app, base_url='http://mock') as client:
        response = await client.post('/run/test-token/jsonrpc/realistic/solana/0', json=request)

    assert response.status_code == 200
    assert SOLANA_BLOCK_MIN_BYTES <= len(response.content) <= SOLANA_BLOCK_MAX_BYTES
    payload = response.json()
    assert payload['id'] == 17
    assert payload['result']['parentSlot'] == 437_297_989


@pytest.mark.anyio
async def test_realistic_solana_head_advances_with_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('INTEGRATION_RUN_TOKEN', 'test-token')
    timestamp = SOLANA_REFERENCE_BLOCK_TIME
    monkeypatch.setattr(mock_endpoint.time, 'time', lambda: timestamp)
    request = {'jsonrpc': '2.0', 'id': 18, 'method': 'getSlot', 'params': [{'commitment': 'finalized'}]}
    async with asgi_client(app, base_url='http://mock') as client:
        first = await client.post('/run/test-token/jsonrpc/realistic/solana/0', json=request)
        timestamp += 2
        second = await client.post('/run/test-token/jsonrpc/realistic/solana/0', json=request)
        fixed = await client.post('/run/test-token/jsonrpc/good/solana/0', json=request)

    assert first.json()['result'] == SOLANA_REFERENCE_SLOT
    assert second.json()['result'] == SOLANA_REFERENCE_SLOT + 5
    assert fixed.json()['result'] == 299_999_999
