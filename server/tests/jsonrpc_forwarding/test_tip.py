from datetime import UTC, datetime

import pytest
from app.model.blockchain import Chain, Network
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.services.public.jsonrpc.tip import extract_tip


@pytest.mark.parametrize(
    ('chain', 'network', 'call', 'raw_result', 'expected'),
    [
        (
            Chain.ETHEREUM,
            Network.MAINNET,
            JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['latest', False]),
            b'{"number":"0x64","transactions":[{"large":"ignored"}]}',
            100,
        ),
        (Chain.SOLANA, Network.MAINNET_BETA, JsonRpcCall(jsonrpc='2.0', id=1, method='getSlot', params=[]), b'123', 123),
        (
            Chain.BITCOIN,
            Network.MAINNET,
            JsonRpcCall(jsonrpc='2.0', id=1, method='getblockchaininfo', params=[]),
            b'{"blocks":456,"bestblockhash":"ignored"}',
            456,
        ),
        (
            Chain.TRON,
            Network.MAINNET,
            JsonRpcCall(jsonrpc='2.0', id=1, method='eth_blockNumber', params=[]),
            b'"0x315"',
            789,
        ),
    ],
)
def test_tip_extractors_decode_only_required_raw_result_fields(
    chain: Chain,
    network: Network,
    call: JsonRpcCall,
    raw_result: bytes,
    expected: int,
) -> None:
    response = JsonRpcSuccessResponse(id=call.request_id(), result=raw_result)

    tip = extract_tip(
        chain=chain,
        network=network,
        call=call,
        response=response,
        observed_at=datetime(2026, 8, 6, tzinfo=UTC),
    )

    assert tip is not None
    assert tip.value == expected
