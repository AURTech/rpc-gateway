import asyncio
import json
from collections.abc import Awaitable
from unittest.mock import patch

import httpx
from scripts.gateway_flow_integration.reference_mock import replies
from scripts.gateway_flow_integration.reference_mock.app import create_reference_app
from scripts.gateway_flow_integration.reference_mock.model import JsonValue, ReferenceBehavior, ReferenceChain, RequestFacts
from scripts.gateway_flow_integration.reference_mock.state import BASE_HEADS

_TOKEN = 'reference-selftest-token'
_EVM_PATH = f'/run/{_TOKEN}/reference/jsonrpc'
_HTTP_PATH = f'/run/{_TOKEN}/reference/http'
_CONTROL_PATH = f'/run/{_TOKEN}/reference'


def _check(value: object, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError('Reference self-test expected a JSON object.')
    return {str(key): item for key, item in value.items()}


def _items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise RuntimeError('Reference self-test expected a JSON array.')
    return [_mapping(item) for item in value]


async def _post_rpc(
    client: httpx.AsyncClient,
    behavior: ReferenceBehavior,
    chain: ReferenceChain,
    method: str,
    params: object,
    request_id: int,
) -> httpx.Response:
    path = f'{_EVM_PATH}/{behavior.value}/{chain.value}/0'
    payload = {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}
    return await client.post(path, json=payload)


async def _protocol_calls(client: httpx.AsyncClient) -> int:
    requests = 0
    ethereum_head = BASE_HEADS[ReferenceChain.ETHEREUM]
    evm_head = await _post_rpc(client, ReferenceBehavior.GOOD, ReferenceChain.ETHEREUM, 'eth_blockNumber', [], 1)
    _check(evm_head.json().get('result') == hex(ethereum_head), 'EVM head fixture mismatch.')
    evm_block = await _post_rpc(
        client,
        ReferenceBehavior.GOOD,
        ReferenceChain.ETHEREUM,
        'debug_traceBlockByNumber',
        [hex(ethereum_head - 1), {'tracer': 'callTracer'}],
        2,
    )
    evm_result = evm_block.json().get('result')
    _check(isinstance(evm_result, list) and bool(evm_result), 'EVM trace fixture is empty or invalid.')
    requests += 2

    bitcoin_head = BASE_HEADS[ReferenceChain.BITCOIN]
    bitcoin_info = await _post_rpc(
        client,
        ReferenceBehavior.GOOD,
        ReferenceChain.BITCOIN,
        'getblockchaininfo',
        [],
        3,
    )
    _check(bitcoin_info.json().get('result', {}).get('blocks') == bitcoin_head, 'UTXO head fixture mismatch.')
    block_hash = await _post_rpc(
        client,
        ReferenceBehavior.GOOD,
        ReferenceChain.BITCOIN,
        'getblockhash',
        [bitcoin_head - 1],
        4,
    )
    block_hash_result = block_hash.json().get('result')
    _check(isinstance(block_hash_result, str), 'UTXO block hash fixture is invalid.')
    bitcoin_block = await _post_rpc(
        client,
        ReferenceBehavior.GOOD,
        ReferenceChain.BITCOIN,
        'getblock',
        [block_hash_result, 3],
        5,
    )
    _check(bitcoin_block.json().get('result', {}).get('height') == bitcoin_head - 1, 'UTXO block fixture mismatch.')
    requests += 3

    solana_head = BASE_HEADS[ReferenceChain.SOLANA]
    slot = await _post_rpc(
        client,
        ReferenceBehavior.GOOD,
        ReferenceChain.SOLANA,
        'getSlot',
        [{'commitment': 'finalized'}],
        6,
    )
    _check(slot.json().get('result') == solana_head, 'Solana head fixture mismatch.')
    solana_block = await _post_rpc(
        client,
        ReferenceBehavior.GOOD,
        ReferenceChain.SOLANA,
        'getBlock',
        [solana_head - 1, {'encoding': 'jsonParsed', 'commitment': 'finalized', 'rewards': False}],
        7,
    )
    solana_result = solana_block.json().get('result')
    _check(isinstance(solana_result, dict) and bool(solana_result.get('transactions')), 'Solana block fixture is invalid.')
    requests += 2

    tron_head = BASE_HEADS[ReferenceChain.TRON]
    tron_root = f'{_HTTP_PATH}/{ReferenceBehavior.GOOD.value}/tron/0'
    tron_info = await client.post(f'{tron_root}/wallet/getnodeinfo', json={})
    solidity_block = tron_info.json().get('solidityBlock')
    _check(isinstance(solidity_block, str) and solidity_block.startswith(f'Num:{tron_head},ID:'), 'TRON head mismatch.')
    tron_block = await client.post(f'{tron_root}/wallet/getblockbynum', json={'num': tron_head - 2, 'visible': True})
    tron_payload = tron_block.json()
    _check(tron_payload.get('block_header', {}).get('raw_data', {}).get('number') == tron_head - 2, 'TRON block mismatch.')
    transactions = tron_payload.get('transactions')
    _check(isinstance(transactions, list) and len(transactions) == 2, 'TRON transaction fixtures are incomplete.')
    trigger = _mapping(transactions[1])
    tx_id = trigger.get('txID')
    _check(isinstance(tx_id, str), 'TRON trigger transaction id is invalid.')
    tx_info = await client.post(f'{tron_root}/wallet/gettransactioninfobyid', json={'value': tx_id, 'visible': True})
    _check(bool(tx_info.json().get('internal_transactions')), 'TRON merge fixture is missing internal transactions.')
    requests += 3
    return requests


async def _fault_calls(client: httpx.AsyncClient) -> int:
    head = BASE_HEADS[ReferenceChain.ETHEREUM]
    good = await _post_rpc(client, ReferenceBehavior.GOOD, ReferenceChain.ETHEREUM, 'eth_blockNumber', [], 100)
    expected_result = good.json().get('result')
    _check(expected_result == hex(head), 'Fault baseline result mismatch.')
    calls = 1
    for offset, behavior in enumerate(ReferenceBehavior, start=1):
        if behavior is ReferenceBehavior.GOOD:
            continue
        response = await _post_rpc(
            client,
            behavior,
            ReferenceChain.ETHEREUM,
            'eth_blockNumber',
            [],
            100 + offset,
        )
        if behavior in {ReferenceBehavior.BAD, ReferenceBehavior.UNAVAILABLE}:
            _check(response.status_code == 503, f'{behavior.value} did not return HTTP 503.')
        elif behavior is ReferenceBehavior.INVALID:
            _check(response.status_code == 200 and response.text == 'not-json', 'Invalid JSON fault mismatch.')
        elif behavior is ReferenceBehavior.WRONG_ID:
            _check(response.json().get('id') != 100 + offset, 'Wrong-id fault preserved the request id.')
        elif behavior is ReferenceBehavior.WRONG_HEIGHT:
            _check(response.json().get('result') != expected_result, 'Wrong-height fault preserved the head.')
        else:
            _check(response.status_code == 200 and response.json().get('result') == expected_result, 'Timeout reply mismatch.')
        calls += 1
    return calls


async def _concurrent_calls(client: httpx.AsyncClient) -> int:
    calls: list[Awaitable[httpx.Response]] = [
        _post_rpc(
            client,
            ReferenceBehavior.TIMEOUT,
            ReferenceChain.ETHEREUM,
            'eth_blockNumber',
            [],
            200 + offset,
        )
        for offset in range(4)
    ]
    responses = await asyncio.gather(*calls)
    _check(all(response.status_code == 200 for response in responses), 'Concurrent timeout requests failed.')
    return len(responses)


async def _run_matrix() -> dict[str, object]:
    app = create_reference_app(_TOKEN, timeout_seconds=0.01)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://reference') as client:
        state = _mapping((await client.get(f'{_CONTROL_PATH}/state')).json())
        ethereum_head = BASE_HEADS[ReferenceChain.ETHEREUM]
        _check(state.get('ethereum') == ethereum_head, 'Reference state did not start at the base head.')

        protocol_requests = await _protocol_calls(client)
        fault_requests = await _fault_calls(client)
        concurrent_requests = await _concurrent_calls(client)

        advanced = _mapping((await client.post(f'{_CONTROL_PATH}/advance/ethereum/3')).json())
        _check(advanced.get('head') == ethereum_head + 3, 'Reference advance did not move the head by three.')
        moved = await _post_rpc(client, ReferenceBehavior.GOOD, ReferenceChain.ETHEREUM, 'eth_blockNumber', [], 300)
        _check(moved.json().get('result') == hex(ethereum_head + 3), 'Advanced EVM head was not observable.')

        report = _mapping((await client.get(f'{_CONTROL_PATH}/ledger')).json())
        requests = _items(report.get('requests'))
        golden = _items(report.get('golden'))
        peak_concurrency = report.get('peak_concurrency')
        _check(report.get('active') == 0, 'Reference ledger retained active requests.')
        _check(isinstance(peak_concurrency, int) and peak_concurrency >= 4, 'Concurrency was not observed.')
        _check(len(requests) == len(golden), 'Request and golden ledgers have different lengths.')
        _check(all(entry.get('fault_contract_match') is True for entry in requests), 'A fault contract did not match.')
        _check(all(entry.get('host') == 'reference' for entry in requests), 'Request Host evidence is incomplete.')
        _check(
            all(isinstance(entry.get('peer_host'), str) and bool(entry.get('peer_host')) for entry in requests),
            'Request peer host evidence is incomplete.',
        )
        _check(
            any(entry.get('method') == 'wallet/gettransactioninfobyid' for entry in requests),
            'TRON txinfo request was not recorded.',
        )

        reset = _mapping((await client.post(f'{_CONTROL_PATH}/reset')).json())
        reset_heads = _mapping(reset.get('heads'))
        _check(reset_heads.get('ethereum') == ethereum_head, 'Reference reset did not restore the base head.')
        empty = _mapping((await client.get(f'{_CONTROL_PATH}/ledger')).json())
        _check(empty.get('requests') == [], 'Reference reset did not clear the request ledger.')

    return {
        'protocol_requests': protocol_requests,
        'fault_requests': fault_requests,
        'concurrent_requests': concurrent_requests,
        'ledger_requests': len(requests),
        'peak_concurrency': report['peak_concurrency'],
    }


async def _run_mutation() -> dict[str, object]:
    def mutated_result(_facts: RequestFacts) -> JsonValue:
        return {'mutated': True}

    with patch.object(replies, 'build_result', mutated_result):
        app = create_reference_app(_TOKEN)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://mutated-reference') as client:
            response = await _post_rpc(
                client,
                ReferenceBehavior.GOOD,
                ReferenceChain.ETHEREUM,
                'eth_blockNumber',
                [],
                999,
            )
            _check(response.json().get('result') == {'mutated': True}, 'Mutation did not alter the fixture response.')
            report = _mapping((await client.get(f'{_CONTROL_PATH}/ledger')).json())
            requests = _items(report.get('requests'))
            _check(len(requests) == 1, 'Mutation control did not record exactly one request.')
            entry = requests[0]
            _check(entry.get('semantic_match') is False, 'Independent golden ledger accepted a mutated response.')
            _check(entry.get('fault_contract_match') is False, 'Mutation control unexpectedly satisfied the good contract.')
    return {'detected': True, 'requests': 1}


async def _execute() -> dict[str, object]:
    matrix = await _run_matrix()
    mutation = await _run_mutation()
    return {'success': True, 'matrix': matrix, 'mutation_control': mutation}


def main() -> None:
    try:
        report = asyncio.run(_execute())
    except Exception as exc:
        report = {'success': False, 'error': f'{type(exc).__name__}: {exc}'}
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
