from scripts.gateway_flow_integration.reference_mock.model import (
    EVM_CHAINS,
    UTXO_CHAINS,
    JsonValue,
    ReferenceChain,
    RequestFacts,
    UnsupportedReferenceRequestError,
)

_EVM_FROM = '0x1111111111111111111111111111111111111111'
_EVM_TO = '0x2222222222222222222222222222222222222222'
_TRON_FROM = 'TJRabPrwbZy45sbavfcjinPJC18kjpRTv8'
_TRON_TO = 'TUEZSdKsoDHQMeZwihtdoBiN46zxhGWYdH'
_SOLANA_FROM = '11111111111111111111111111111111'
_SOLANA_TO = 'SysvarRent111111111111111111111111111111111'


def _evm_result(facts: RequestFacts) -> JsonValue:
    if facts.method == 'eth_blockNumber':
        return hex(facts.head)
    if facts.method != 'debug_traceBlockByNumber':
        raise UnsupportedReferenceRequestError(f'Unsupported EVM method: {facts.method}.')
    height = facts.target_height
    return [
        {
            'txHash': f'0x{height:064x}',
            'result': {
                'type': 'CALL',
                'from': _EVM_FROM,
                'to': _EVM_TO,
                'input': '0x',
                'value': hex(height + 1),
                'gasUsed': '0x5208',
            },
        }
    ]


def _utxo_result(facts: RequestFacts) -> JsonValue:
    if facts.method == 'getblockchaininfo':
        return {'blocks': facts.head, 'headers': facts.head, 'initialblockdownload': False}
    if facts.method == 'getblockhash':
        return f'{facts.target_height:064x}'
    if facts.method != 'getblock':
        raise UnsupportedReferenceRequestError(f'Unsupported UTXO method: {facts.method}.')
    height = facts.target_height
    return {
        'hash': f'{height:064x}',
        'height': height,
        'time': 1_700_000_000 + height,
        'tx': [
            {
                'txid': f'{height + 1:064x}',
                'vin': [
                    {
                        'txid': f'{height - 1:064x}',
                        'vout': 0,
                        'prevout': {
                            'value': 2.0,
                            'scriptPubKey': {'address': f'{facts.chain.value}-from-{height}'},
                        },
                    }
                ],
                'vout': [
                    {
                        'value': 1.5,
                        'n': 0,
                        'scriptPubKey': {'address': f'{facts.chain.value}-to-{height}'},
                    }
                ],
            }
        ],
    }


def _solana_result(facts: RequestFacts) -> JsonValue:
    if facts.method == 'getSlot':
        return facts.head
    if facts.method != 'getBlock':
        raise UnsupportedReferenceRequestError(f'Unsupported Solana method: {facts.method}.')
    height = facts.target_height
    return {
        'blockHeight': height,
        'blockTime': 1_700_000_000 + height,
        'blockhash': f'reference-block-{height:020d}',
        'previousBlockhash': f'reference-block-{height - 1:020d}',
        'parentSlot': max(0, height - 1),
        'transactions': [
            {
                'meta': {
                    'err': None,
                    'fee': 5000,
                    'innerInstructions': [],
                    'postTokenBalances': [],
                },
                'transaction': {
                    'signatures': [f'reference-signature-{height:020d}'],
                    'message': {
                        'accountKeys': [_SOLANA_FROM, _SOLANA_TO],
                        'instructions': [
                            {
                                'program': 'system',
                                'parsed': {
                                    'type': 'transfer',
                                    'info': {
                                        'lamports': height + 1,
                                        'source': _SOLANA_FROM,
                                        'destination': _SOLANA_TO,
                                    },
                                },
                            }
                        ],
                    },
                },
            }
        ],
    }


def _tron_result(facts: RequestFacts) -> JsonValue:
    if facts.method == 'wallet/getnodeinfo':
        return {'solidityBlock': f'Num:{facts.head},ID:{facts.head:064x}', 'block': f'Num:{facts.head},ID:{facts.head:064x}'}
    if facts.method == 'wallet/gettransactioninfobyid':
        return {
            'id': f'{facts.target_height:064x}',
            'fee': 1000,
            'blockNumber': facts.target_height,
            'log': [],
            'internal_transactions': [
                {
                    'caller_address': _TRON_FROM,
                    'transferTo_address': _TRON_TO,
                    'callValueInfo': [{'callValue': facts.target_height + 2}],
                }
            ],
        }
    if facts.method != 'wallet/getblockbynum':
        raise UnsupportedReferenceRequestError(f'Unsupported TRON path: {facts.method}.')
    height = facts.target_height
    return {
        'blockID': f'{height:064x}',
        'block_header': {'raw_data': {'number': height, 'timestamp': (1_700_000_000 + height) * 1000}},
        'transactions': [
            {
                'txID': f'{height + 1:064x}',
                'ret': [{'contractRet': 'SUCCESS'}],
                'raw_data': {
                    'contract': [
                        {
                            'type': 'TransferContract',
                            'parameter': {
                                'value': {
                                    'owner_address': _TRON_FROM,
                                    'to_address': _TRON_TO,
                                    'amount': height + 1,
                                }
                            },
                        }
                    ]
                },
            },
            {
                'txID': f'{height:064x}',
                'ret': [{'contractRet': 'SUCCESS'}],
                'raw_data': {
                    'contract': [
                        {
                            'type': 'TriggerSmartContract',
                            'parameter': {
                                'value': {
                                    'owner_address': _TRON_FROM,
                                    'contract_address': _TRON_TO,
                                    'data': 'deadbeef',
                                }
                            },
                        }
                    ]
                },
            },
        ],
    }


def build_result(facts: RequestFacts) -> JsonValue:
    if facts.chain in EVM_CHAINS:
        return _evm_result(facts)
    if facts.chain in UTXO_CHAINS:
        return _utxo_result(facts)
    if facts.chain is ReferenceChain.SOLANA:
        return _solana_result(facts)
    if facts.chain is ReferenceChain.TRON:
        return _tron_result(facts)
    raise UnsupportedReferenceRequestError(f'Unsupported reference chain: {facts.chain.value}.')
