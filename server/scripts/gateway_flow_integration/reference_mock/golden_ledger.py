import hashlib
from dataclasses import dataclass

import orjson
from scripts.gateway_flow_integration.reference_mock.model import (
    EVM_CHAINS,
    UTXO_CHAINS,
    JsonValue,
    ReferenceChain,
    ReferenceTransport,
    RequestFacts,
    UnsupportedReferenceRequestError,
)

# This module intentionally does not import fixtures or fault transforms. It is an independent oracle.
_FROM_EVM = '0x1111111111111111111111111111111111111111'
_TO_EVM = '0x2222222222222222222222222222222222222222'
_FROM_TRON = 'TJRabPrwbZy45sbavfcjinPJC18kjpRTv8'
_TO_TRON = 'TUEZSdKsoDHQMeZwihtdoBiN46zxhGWYdH'
_FROM_SOLANA = '11111111111111111111111111111111'
_TO_SOLANA = 'SysvarRent111111111111111111111111111111111'


def digest_payload(value: JsonValue) -> str:
    encoded = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _golden_evm(facts: RequestFacts) -> JsonValue:
    if facts.method == 'eth_blockNumber':
        return hex(facts.head)
    if facts.method != 'debug_traceBlockByNumber':
        raise UnsupportedReferenceRequestError(f'Golden ledger does not support EVM method: {facts.method}.')
    height = facts.target_height
    trace: dict[str, JsonValue] = {
        'type': 'CALL',
        'from': _FROM_EVM,
        'to': _TO_EVM,
        'input': '0x',
        'value': hex(height + 1),
        'gasUsed': '0x5208',
    }
    return [{'txHash': '0x' + format(height, '064x'), 'result': trace}]


def _golden_utxo(facts: RequestFacts) -> JsonValue:
    height = facts.target_height
    if facts.method == 'getblockchaininfo':
        return {'blocks': facts.head, 'headers': facts.head, 'initialblockdownload': False}
    if facts.method == 'getblockhash':
        return format(height, '064x')
    if facts.method != 'getblock':
        raise UnsupportedReferenceRequestError(f'Golden ledger does not support UTXO method: {facts.method}.')
    previous_tx = format(height - 1, '064x')
    tx_id = format(height + 1, '064x')
    return {
        'hash': format(height, '064x'),
        'height': height,
        'time': 1_700_000_000 + height,
        'tx': [
            {
                'txid': tx_id,
                'vin': [
                    {
                        'txid': previous_tx,
                        'vout': 0,
                        'prevout': {
                            'value': 2.0,
                            'scriptPubKey': {'address': facts.chain.value + '-from-' + str(height)},
                        },
                    }
                ],
                'vout': [
                    {
                        'value': 1.5,
                        'n': 0,
                        'scriptPubKey': {'address': facts.chain.value + '-to-' + str(height)},
                    }
                ],
            }
        ],
    }


def _golden_solana(facts: RequestFacts) -> JsonValue:
    if facts.method == 'getSlot':
        return facts.head
    if facts.method != 'getBlock':
        raise UnsupportedReferenceRequestError(f'Golden ledger does not support Solana method: {facts.method}.')
    height = facts.target_height
    instruction: dict[str, JsonValue] = {
        'program': 'system',
        'parsed': {
            'type': 'transfer',
            'info': {'lamports': height + 1, 'source': _FROM_SOLANA, 'destination': _TO_SOLANA},
        },
    }
    return {
        'blockHeight': height,
        'blockTime': 1_700_000_000 + height,
        'blockhash': 'reference-block-' + str(height).zfill(20),
        'previousBlockhash': 'reference-block-' + str(height - 1).zfill(20),
        'parentSlot': max(0, height - 1),
        'transactions': [
            {
                'meta': {'err': None, 'fee': 5000, 'innerInstructions': [], 'postTokenBalances': []},
                'transaction': {
                    'signatures': ['reference-signature-' + str(height).zfill(20)],
                    'message': {'accountKeys': [_FROM_SOLANA, _TO_SOLANA], 'instructions': [instruction]},
                },
            }
        ],
    }


def _golden_tron(facts: RequestFacts) -> JsonValue:
    height = facts.target_height
    if facts.method == 'wallet/getnodeinfo':
        identifier = format(facts.head, '064x')
        return {'solidityBlock': f'Num:{facts.head},ID:{identifier}', 'block': f'Num:{facts.head},ID:{identifier}'}
    if facts.method == 'wallet/gettransactioninfobyid':
        internal: dict[str, JsonValue] = {
            'caller_address': _FROM_TRON,
            'transferTo_address': _TO_TRON,
            'callValueInfo': [{'callValue': height + 2}],
        }
        return {
            'id': format(height, '064x'),
            'fee': 1000,
            'blockNumber': height,
            'log': [],
            'internal_transactions': [internal],
        }
    if facts.method != 'wallet/getblockbynum':
        raise UnsupportedReferenceRequestError(f'Golden ledger does not support TRON path: {facts.method}.')
    transfer: dict[str, JsonValue] = {
        'type': 'TransferContract',
        'parameter': {
            'value': {'owner_address': _FROM_TRON, 'to_address': _TO_TRON, 'amount': height + 1},
        },
    }
    trigger: dict[str, JsonValue] = {
        'type': 'TriggerSmartContract',
        'parameter': {
            'value': {
                'owner_address': _FROM_TRON,
                'contract_address': _TO_TRON,
                'data': 'deadbeef',
            },
        },
    }
    return {
        'blockID': format(height, '064x'),
        'block_header': {'raw_data': {'number': height, 'timestamp': (1_700_000_000 + height) * 1000}},
        'transactions': [
            {
                'txID': format(height + 1, '064x'),
                'ret': [{'contractRet': 'SUCCESS'}],
                'raw_data': {'contract': [transfer]},
            },
            {
                'txID': format(height, '064x'),
                'ret': [{'contractRet': 'SUCCESS'}],
                'raw_data': {'contract': [trigger]},
            },
        ],
    }


def build_golden_payload(facts: RequestFacts) -> JsonValue:
    if facts.chain in EVM_CHAINS:
        result = _golden_evm(facts)
    elif facts.chain in UTXO_CHAINS:
        result = _golden_utxo(facts)
    elif facts.chain is ReferenceChain.SOLANA:
        result = _golden_solana(facts)
    elif facts.chain is ReferenceChain.TRON:
        result = _golden_tron(facts)
    else:
        raise UnsupportedReferenceRequestError(f'Golden ledger does not support chain: {facts.chain.value}.')
    if facts.transport is ReferenceTransport.JSONRPC:
        return {'jsonrpc': '2.0', 'id': facts.request_id, 'result': result}
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class GoldenEntry:
    sequence: int
    status_code: int
    response_id: str | int | None
    payload_digest: str


def make_golden_entry(sequence: int, facts: RequestFacts) -> GoldenEntry:
    payload = build_golden_payload(facts)
    return GoldenEntry(
        sequence=sequence,
        status_code=200,
        response_id=facts.request_id,
        payload_digest=digest_payload(payload),
    )
