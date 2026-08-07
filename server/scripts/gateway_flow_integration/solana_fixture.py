import hashlib
from functools import lru_cache

import orjson

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

SOLANA_BLOCK_MIN_BYTES = 8 * 1024 * 1024
SOLANA_BLOCK_TARGET_BYTES = 10 * 1024 * 1024
SOLANA_BLOCK_MAX_BYTES = 12 * 1024 * 1024

_BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_SYSTEM_PROGRAM = '11111111111111111111111111111111'
_TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
_COMPUTE_BUDGET_PROGRAM = 'ComputeBudget111111111111111111111111111111'
SOLANA_REFERENCE_SLOT = 437_297_988
SOLANA_REFERENCE_BLOCK_HEIGHT = 415_352_611
SOLANA_REFERENCE_BLOCK_TIME = 1_785_898_667


def _base58_bytes(seed: str, size: int) -> str:
    raw = bytearray(hashlib.shake_256(seed.encode()).digest(size))
    raw[0] = 255
    number = int.from_bytes(raw)
    encoded = ''
    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58_ALPHABET[remainder] + encoded
    return encoded


def _account_keys(slot: int, index: int) -> list[str]:
    generated = [_base58_bytes(f'account:{slot}:{index}:{position}', 32) for position in range(9)]
    return [generated[0], generated[1], _SYSTEM_PROGRAM, _TOKEN_PROGRAM, _COMPUTE_BUDGET_PROGRAM, *generated[2:]]


def _token_balance(account_index: int, mint: str, owner: str, amount: int) -> dict[str, JsonValue]:
    return {
        'accountIndex': account_index,
        'mint': mint,
        'owner': owner,
        'programId': _TOKEN_PROGRAM,
        'uiTokenAmount': {
            'amount': str(amount),
            'decimals': 6,
            'uiAmount': amount / 1_000_000,
            'uiAmountString': f'{amount / 1_000_000:.6f}',
        },
    }


def _compiled_message(keys: list[str], slot: int, index: int) -> dict[str, JsonValue]:
    account_keys: list[JsonValue] = [*keys]
    return {
        'accountKeys': account_keys,
        'addressTableLookups': [
            {
                'accountKey': keys[5],
                'readonlyIndexes': [1, 2, 4, 7],
                'writableIndexes': [0, 3, 5],
            }
        ],
        'header': {
            'numReadonlySignedAccounts': 0,
            'numReadonlyUnsignedAccounts': 4,
            'numRequiredSignatures': 1,
        },
        'instructions': [
            {'accounts': [0, 1], 'data': _base58_bytes(f'transfer:{slot}:{index}', 96), 'programIdIndex': 2},
            {'accounts': [0, 1, 6, 7], 'data': _base58_bytes(f'token:{slot}:{index}', 128), 'programIdIndex': 3},
            {'accounts': [], 'data': _base58_bytes(f'compute:{slot}:{index}', 16), 'programIdIndex': 4},
        ],
        'recentBlockhash': _base58_bytes(f'recent:{slot}:{index}', 32),
    }


def _parsed_message(keys: list[str], slot: int, index: int) -> dict[str, JsonValue]:
    account_keys: list[JsonValue] = [
        {
            'pubkey': key,
            'signer': position == 0,
            'source': 'transaction' if position < 5 else 'lookupTable',
            'writable': position in {0, 1, 5, 6, 7},
        }
        for position, key in enumerate(keys)
    ]
    return {
        'accountKeys': account_keys,
        'instructions': [
            {
                'parsed': {
                    'info': {'destination': keys[1], 'lamports': slot + index + 1, 'source': keys[0]},
                    'type': 'transfer',
                },
                'program': 'system',
                'programId': _SYSTEM_PROGRAM,
                'stackHeight': None,
            },
            {
                'parsed': {
                    'info': {
                        'amount': str(1_000_000 + index),
                        'authority': keys[0],
                        'destination': keys[7],
                        'source': keys[6],
                    },
                    'type': 'transfer',
                },
                'program': 'spl-token',
                'programId': _TOKEN_PROGRAM,
                'stackHeight': None,
            },
            {
                'accounts': [],
                'data': _base58_bytes(f'compute:{slot}:{index}', 16),
                'programId': _COMPUTE_BUDGET_PROGRAM,
                'stackHeight': None,
            },
        ],
        'recentBlockhash': _base58_bytes(f'recent:{slot}:{index}', 32),
    }


def _transaction(slot: int, index: int, encoding: str) -> dict[str, JsonValue]:
    keys = _account_keys(slot, index)
    mint = keys[8]
    amount = 5_000_000 + index
    inner_instruction: dict[str, JsonValue]
    if encoding == 'jsonParsed':
        parsed_accounts: list[JsonValue] = [keys[0], keys[1], keys[6], keys[7]]
        inner_instruction = {
            'accounts': parsed_accounts,
            'data': _base58_bytes(f'inner:{slot}:{index}', 160),
            'programId': _TOKEN_PROGRAM,
            'stackHeight': 2,
        }
    else:
        inner_instruction = {
            'accounts': [0, 1, 6, 7],
            'data': _base58_bytes(f'inner:{slot}:{index}', 160),
            'programIdIndex': 3,
            'stackHeight': 2,
        }
    log_messages: list[JsonValue] = [
        'Program ComputeBudget111111111111111111111111111111 invoke [1]',
        'Program ComputeBudget111111111111111111111111111111 success',
        'Program 11111111111111111111111111111111 invoke [1]',
        f'Program log: transfer {slot + index + 1} lamports',
        'Program 11111111111111111111111111111111 success',
        f'Program {_TOKEN_PROGRAM} invoke [1]',
        'Program log: Instruction: Transfer',
        f'Program log: source={keys[6]} destination={keys[7]} amount={amount}',
        f'Program {_TOKEN_PROGRAM} consumed 4645 of 196850 compute units',
        f'Program {_TOKEN_PROGRAM} success',
    ]
    message = _parsed_message(keys, slot, index) if encoding == 'jsonParsed' else _compiled_message(keys, slot, index)
    inner_items: list[JsonValue] = []
    inner_items.append(inner_instruction)
    inner_group: dict[str, JsonValue] = {'index': 1, 'instructions': inner_items}
    inner_instructions: list[JsonValue] = []
    inner_instructions.append(inner_group)
    post_balances: list[JsonValue] = [2_000_000_000 - position * 1000 for position in range(len(keys))]
    post_token_balances: list[JsonValue] = [_token_balance(7, mint, keys[1], amount)]
    pre_balances: list[JsonValue] = [2_000_005_000 - position * 1000 for position in range(len(keys))]
    pre_token_balances: list[JsonValue] = [_token_balance(6, mint, keys[0], amount)]
    meta: dict[str, JsonValue] = {
        'computeUnitsConsumed': 9876 + index % 2048,
        'costUnits': 12345 + index % 2048,
        'err': None,
        'fee': 5000,
        'innerInstructions': inner_instructions,
        'logMessages': log_messages,
        'postBalances': post_balances,
        'postTokenBalances': post_token_balances,
        'preBalances': pre_balances,
        'preTokenBalances': pre_token_balances,
        'rewards': [],
        'status': {'Ok': None},
    }
    transaction: dict[str, JsonValue] = {
        'message': message,
        'signatures': [_base58_bytes(f'signature:{slot}:{index}', 64)],
    }
    return {
        'meta': meta,
        'transaction': transaction,
        'version': 'legacy' if index % 3 else 0,
    }


def _block_base(slot: int) -> dict[str, JsonValue]:
    slot_delta = slot - SOLANA_REFERENCE_SLOT
    return {
        'blockHeight': max(0, SOLANA_REFERENCE_BLOCK_HEIGHT + slot_delta),
        'blockTime': SOLANA_REFERENCE_BLOCK_TIME + slot_delta * 2 // 5,
        'blockhash': _base58_bytes(f'block:{slot}', 32),
        'parentSlot': max(0, slot - 1),
        'previousBlockhash': _base58_bytes(f'block:{slot - 1}', 32),
        'transactions': [],
    }


@lru_cache(maxsize=2)
def _build_transactions(encoding: str, target_bytes: int) -> list[JsonValue]:
    block = _block_base(SOLANA_REFERENCE_SLOT)
    sample = _transaction(SOLANA_REFERENCE_SLOT, 0, encoding)
    base_bytes = len(orjson.dumps(block))
    transaction_bytes = len(orjson.dumps(sample)) + 1
    transaction_count = max(1, (target_bytes - base_bytes) // transaction_bytes)
    return [_transaction(SOLANA_REFERENCE_SLOT, index, encoding) for index in range(transaction_count)]


def build_solana_block(
    slot: int,
    encoding: str = 'jsonParsed',
    target_bytes: int = SOLANA_BLOCK_TARGET_BYTES,
) -> dict[str, JsonValue]:
    if slot < 0:
        raise ValueError('Solana slot must not be negative.')
    if encoding not in {'json', 'jsonParsed'}:
        raise ValueError('Solana fixture encoding must be json or jsonParsed.')
    if target_bytes <= 0:
        raise ValueError('Solana fixture target size must be positive.')

    block = _block_base(slot)
    block['transactions'] = _build_transactions(encoding, target_bytes)
    return block
