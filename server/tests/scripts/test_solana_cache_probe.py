import httpx
import pytest
from scripts.solana_cache_probe import (
    ScannerResult,
    _get_block,
    _get_slot,
    _summary,
    _validate_hits,
)


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


@pytest.mark.anyio
async def test_slot_request_uses_finalized_commitment() -> None:
    async def response(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert payload == b'{"jsonrpc":"2.0","id":1,"method":"getSlot","params":[{"commitment":"finalized"}]}'
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': 442_266_263})

    async with _client(httpx.MockTransport(response)) as client:
        assert await _get_slot(client, 'https://gateway.test/key') == 442_266_263


@pytest.mark.anyio
async def test_block_request_matches_cache_policy_shape() -> None:
    async def response(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert payload == (
            b'{"jsonrpc":"2.0","id":1,"method":"getBlock","params":[442266263,{"encoding":"jsonParsed",'
            b'"rewards":false,"commitment":"finalized","maxSupportedTransactionVersion":0}]}'
        )
        return httpx.Response(
            200,
            headers={'X-RPC-Gateway-Cache': 'HIT'},
            json={'jsonrpc': '2.0', 'id': 1, 'result': {'blockHeight': 442_266_262}},
        )

    async with _client(httpx.MockTransport(response)) as client:
        assert await _get_block(client, 'https://gateway.test/key', 442_266_263) is True


def test_cache_validation_accepts_one_hit_per_overlapping_slot() -> None:
    results = (
        ScannerResult(name='scanner-1', slots=frozenset({100, 101, 102}), block_requests=3, block_hits=0),
        ScannerResult(name='scanner-2', slots=frozenset({100, 101, 102}), block_requests=3, block_hits=3),
    )

    _validate_hits(results)
    assert _summary(results) == (
        'scanner-1: requests=3, hits=0; scanner-2: requests=3, hits=3; '
        'total_requests=6, unique_slots=3, overlap=3, hits=3, hit_rate=50.0%'
    )


def test_cache_validation_rejects_missing_hits() -> None:
    results = (
        ScannerResult(name='scanner-1', slots=frozenset({100, 101}), block_requests=2, block_hits=0),
        ScannerResult(name='scanner-2', slots=frozenset({100, 101}), block_requests=2, block_hits=1),
    )

    with pytest.raises(RuntimeError, match='Expected at least 2 cache hits'):
        _validate_hits(results)
