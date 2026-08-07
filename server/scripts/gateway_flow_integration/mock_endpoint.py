import asyncio
import hashlib
import hmac
import os
import socket
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import orjson
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from scripts.gateway_flow_integration.solana_fixture import (
    SOLANA_REFERENCE_BLOCK_TIME,
    SOLANA_REFERENCE_SLOT,
    build_solana_block,
)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_COUNTERS: Counter[str] = Counter()
_PEERS: Counter[str] = Counter()
_STATE_LOCK = asyncio.Lock()
_LEDGER: list['LedgerEntry'] = []
_NEXT_EVENT_SEQUENCE = 1
_ACTIVE_REQUESTS = 0
_BARRIERS: dict[str, 'BarrierState'] = {}
_HEIGHTS = {
    'ethereum': 20_000_000,
    'polygon': 60_000_000,
    'bsc': 40_000_000,
    'arbitrum': 250_000_000,
    'optimism': 130_000_000,
    'base': 25_000_000,
    'solana': 300_000_000,
    'bitcoin': 900_000,
    'litecoin': 3_000_000,
    'tron': 75_000_000,
}
_SOLANA_SLOT_SECONDS = 0.4


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerTicket:
    started_sequence: int
    started_at: float
    peer: str
    transport: str
    behavior: str
    chain: str
    source: int
    method: str
    request_id: str | int | None
    request_digest: str
    params_digest: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerEntry:
    started_sequence: int
    finished_sequence: int
    peer: str
    transport: str
    behavior: str
    chain: str
    source: int
    method: str
    request_id: str | int | None
    request_digest: str
    params_digest: str
    status_code: int
    response_digest: str
    elapsed_ms: float


@dataclass(slots=True, kw_only=True)
class BarrierState:
    event: asyncio.Event
    waiters: int = 0


def _digest_json(value: object) -> str:
    encoded = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _token_matches(token: str) -> bool:
    expected = os.environ.get('INTEGRATION_RUN_TOKEN', '')
    return bool(expected) and hmac.compare_digest(token, expected)


async def _record(*parts: object) -> None:
    key = ':'.join(str(part) for part in parts)
    async with _STATE_LOCK:
        _COUNTERS[key] += 1


async def _record_peer(request: Request) -> str:
    peer = request.client.host if request.client is not None else 'unknown'
    async with _STATE_LOCK:
        _PEERS[peer] += 1
    return peer


async def _begin_ledger(
    *,
    peer: str,
    transport: str,
    behavior: str,
    chain: str,
    source: int,
    method: str,
    request_id: str | int | None,
    request_payload: object,
    params: object,
) -> LedgerTicket:
    global _ACTIVE_REQUESTS, _NEXT_EVENT_SEQUENCE
    async with _STATE_LOCK:
        started_sequence = _NEXT_EVENT_SEQUENCE
        _NEXT_EVENT_SEQUENCE += 1
        _ACTIVE_REQUESTS += 1
    return LedgerTicket(
        started_sequence=started_sequence,
        started_at=time.monotonic(),
        peer=peer,
        transport=transport,
        behavior=behavior,
        chain=chain,
        source=source,
        method=method,
        request_id=request_id,
        request_digest=_digest_json(request_payload),
        params_digest=_digest_json(params),
    )


async def _finish_ledger(
    ticket: LedgerTicket,
    *,
    status_code: int,
    response_payload: object | None = None,
    response_body: bytes | None = None,
) -> None:
    global _ACTIVE_REQUESTS, _NEXT_EVENT_SEQUENCE
    if (response_payload is None) == (response_body is None):
        raise ValueError('Exactly one ledger response value is required.')
    response_digest = _digest_json(response_payload) if response_payload is not None else _digest_bytes(response_body or b'')
    async with _STATE_LOCK:
        finished_sequence = _NEXT_EVENT_SEQUENCE
        _NEXT_EVENT_SEQUENCE += 1
        _ACTIVE_REQUESTS -= 1
        _LEDGER.append(
            LedgerEntry(
                started_sequence=ticket.started_sequence,
                finished_sequence=finished_sequence,
                peer=ticket.peer,
                transport=ticket.transport,
                behavior=ticket.behavior,
                chain=ticket.chain,
                source=ticket.source,
                method=ticket.method,
                request_id=ticket.request_id,
                request_digest=ticket.request_digest,
                params_digest=ticket.params_digest,
                status_code=status_code,
                response_digest=response_digest,
                elapsed_ms=round((time.monotonic() - ticket.started_at) * 1000, 3),
            )
        )


async def _plain_reply(
    ticket: LedgerTicket,
    body: bytes,
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
) -> PlainTextResponse:
    await _finish_ledger(ticket, status_code=status_code, response_body=body)
    return PlainTextResponse(body, status_code=status_code, headers=headers)


async def _json_reply(
    ticket: LedgerTicket,
    payload: object,
    status_code: int = 200,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    await _finish_ledger(ticket, status_code=status_code, response_payload=payload)
    return JSONResponse(payload, status_code=status_code, headers=headers)


def _replica_addresses() -> dict[str, list[str]]:
    addresses: dict[str, list[str]] = {}
    for replica in ('api-a', 'api-b'):
        try:
            values = socket.gethostbyname_ex(replica)[2]
        except OSError:
            values = []
        addresses[replica] = sorted(set(values))
    return addresses


def _source_height(chain: str, source: int) -> int:
    return _HEIGHTS[chain] + source - 1


def _jsonrpc_result(chain: str, source: int, method: str, params: object) -> object:
    height = _source_height(chain, source)
    if method == 'eth_blockNumber':
        return hex(height)
    if method == 'eth_getBlockByNumber':
        requested = params[0] if isinstance(params, list) and params else None
        requested_height = int(requested, 16) if isinstance(requested, str) and requested.startswith('0x') else height
        return {'number': hex(requested_height), 'hash': f'0x{requested_height:064x}', 'source': source}
    if method in {'getSlot', 'getBlockHeight'}:
        return height
    if method == 'getblockchaininfo':
        return {'blocks': height, 'headers': height, 'initialblockdownload': False}
    if method == 'getblockcount':
        return height
    if method == 'getblockhash':
        requested = params[0] if isinstance(params, list) and params else height
        requested_height = requested if isinstance(requested, int) and not isinstance(requested, bool) else height
        return f'{requested_height:064x}'
    if method == 'getblock':
        block_hash = params[0] if isinstance(params, list) and params else ''
        try:
            block_height = int(block_hash, 16) if isinstance(block_hash, str) else height
        except ValueError:
            block_height = height
        return {'height': block_height, 'hash': block_hash, 'source': source}
    if method == 'getBlock':
        slot = params[0] if isinstance(params, list) and params else height
        block_height = max(0, slot - 1) if isinstance(slot, int) else height
        return {'blockHeight': block_height, 'blockTime': 1_700_000_000, 'source': source}
    return {'chain': chain, 'source': source, 'method': method, 'params': params}


def _realistic_solana_slot(timestamp: float | None = None) -> int:
    observed_at = time.time() if timestamp is None else timestamp
    elapsed = max(0.0, observed_at - SOLANA_REFERENCE_BLOCK_TIME)
    return SOLANA_REFERENCE_SLOT + int(elapsed / _SOLANA_SLOT_SECONDS)


def _realistic_solana_result(method: str, params: object) -> object:
    if method in {'getSlot', 'getBlockHeight'}:
        return _realistic_solana_slot()
    if method != 'getBlock' or not isinstance(params, list) or not params:
        return {'chain': 'solana', 'method': method, 'params': params}
    slot = params[0]
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        return {'chain': 'solana', 'method': method, 'params': params}
    encoding = 'json'
    if len(params) > 1 and isinstance(params[1], dict):
        for key, value in params[1].items():
            if key == 'encoding' and isinstance(value, str) and value in {'json', 'jsonParsed'}:
                encoding = value
                break
    return build_solana_block(slot, encoding)


@app.get('/__integration/health')
async def health() -> dict[str, bool]:
    return {'ok': True}


@app.get('/__integration/counters')
async def counters() -> dict[str, int]:
    async with _STATE_LOCK:
        return dict(_COUNTERS)


@app.get('/__integration/peers')
async def peers() -> dict[str, object]:
    async with _STATE_LOCK:
        observed = dict(_PEERS)
    return {'observed': observed, 'replicas': _replica_addresses()}


@app.get('/__integration/ledger')
async def ledger() -> dict[str, object]:
    async with _STATE_LOCK:
        entries = sorted(_LEDGER, key=lambda entry: entry.started_sequence)
        return {
            'active': _ACTIVE_REQUESTS,
            'entries': [asdict(entry) for entry in entries],
            'next_event_sequence': _NEXT_EVENT_SEQUENCE,
        }


@app.delete('/__integration/ledger')
async def clear_ledger() -> JSONResponse:
    global _NEXT_EVENT_SEQUENCE
    async with _STATE_LOCK:
        if _ACTIVE_REQUESTS:
            return JSONResponse({'cleared': False, 'active': _ACTIVE_REQUESTS}, status_code=409)
        _LEDGER.clear()
        _NEXT_EVENT_SEQUENCE = 1
    return JSONResponse({'cleared': True})


@app.put('/__integration/barriers/{name}')
async def arm_barrier(name: str) -> JSONResponse:
    async with _STATE_LOCK:
        saved = _BARRIERS.get(name)
        if saved is not None and saved.waiters:
            return JSONResponse({'armed': False, 'waiters': saved.waiters}, status_code=409)
        _BARRIERS[name] = BarrierState(event=asyncio.Event())
    return JSONResponse({'armed': True, 'name': name})


@app.get('/__integration/barriers/{name}')
async def barrier(name: str) -> JSONResponse:
    async with _STATE_LOCK:
        saved = _BARRIERS.get(name)
        if saved is None:
            return JSONResponse({'armed': False, 'waiters': 0, 'released': False}, status_code=404)
        return JSONResponse({'armed': True, 'waiters': saved.waiters, 'released': saved.event.is_set()})


@app.post('/__integration/barriers/{name}/release')
async def release_barrier(name: str) -> JSONResponse:
    async with _STATE_LOCK:
        saved = _BARRIERS.get(name)
        if saved is None:
            return JSONResponse({'released': False}, status_code=404)
        saved.event.set()
        waiters = saved.waiters
    return JSONResponse({'released': True, 'waiters': waiters})


@app.delete('/__integration/counters')
async def clear_counters() -> dict[str, bool]:
    async with _STATE_LOCK:
        _COUNTERS.clear()
        _PEERS.clear()
    return {'cleared': True}


@app.post('/run/{token}/jsonrpc/{behavior}/{chain}/{source}')
async def jsonrpc(token: str, behavior: str, chain: str, source: int, request: Request):
    if not _token_matches(token) or chain not in _HEIGHTS:
        return PlainTextResponse('Not found', status_code=404)
    try:
        payload: Any = await request.json()
    except Exception:
        payload = {}
    method = payload.get('method') if isinstance(payload, dict) else None
    request_id = payload.get('id') if isinstance(payload, dict) else None
    params = payload.get('params') if isinstance(payload, dict) else None
    peer = await _record_peer(request)
    await _record('jsonrpc', behavior, chain, source, method or 'invalid')
    ticket = await _begin_ledger(
        peer=peer,
        transport='jsonrpc',
        behavior=behavior,
        chain=chain,
        source=source,
        method=method if isinstance(method, str) else 'invalid',
        request_id=request_id if isinstance(request_id, str | int) and not isinstance(request_id, bool) else None,
        request_payload=payload,
        params=params,
    )
    if behavior == 'unavailable':
        return await _plain_reply(ticket, b'upstream unavailable', 503)
    if behavior == 'invalid':
        return await _plain_reply(ticket, b'not-json', 200)
    if behavior == 'timeout':
        await asyncio.sleep(11.5)
        return await _plain_reply(ticket, b'late', 200)
    if behavior == 'trace_503' and isinstance(method, str) and method.startswith(('debug_', 'trace_')):
        return await _plain_reply(ticket, b'trace unavailable', 503)
    if behavior == 'rate_limit':
        error_payload = {
            'jsonrpc': '2.0',
            'id': request_id,
            'error': {'code': -32099, 'message': 'Upstream rate limited.'},
        }
        return await _json_reply(ticket, error_payload, 429, headers={'Retry-After': '1'})
    if behavior == 'oversized':
        oversized = {'jsonrpc': '2.0', 'id': request_id, 'result': 'x' * (8 * 1024 * 1024 + 1024)}
        return await _json_reply(ticket, oversized)
    if behavior == 'barrier_low':
        async with _STATE_LOCK:
            low_barrier = _BARRIERS.get('tip-low')
            if low_barrier is not None:
                low_barrier.waiters += 1
        if low_barrier is None:
            return await _plain_reply(ticket, b'Barrier not armed', 409)
        try:
            await low_barrier.event.wait()
        finally:
            async with _STATE_LOCK:
                low_barrier.waiters -= 1
    elif behavior not in {'good', 'realistic', 'wrong_height', 'trace_503'}:
        return await _plain_reply(ticket, b'Not found', 404)
    if not isinstance(payload, dict) or not isinstance(method, str):
        return await _plain_reply(ticket, b'Not found', 404)
    if method in {'eth_blockNumber', 'getSlot', 'getblockchaininfo'}:
        await asyncio.sleep(0.3)
    if method == 'eth_getBlockByNumber' and payload.get('params') == ['latest', False]:
        await asyncio.sleep(0.1)
    if method == 'integration_error' or method.startswith('integration_usage_failure_'):
        error_payload = {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32602, 'message': 'Invalid params.'}}
        return await _json_reply(ticket, error_payload)
    if behavior == 'realistic' and chain == 'solana':
        result = _realistic_solana_result(method, payload.get('params'))
    elif behavior == 'realistic':
        return await _plain_reply(ticket, b'Not found', 404)
    else:
        result = _jsonrpc_result(chain, source, method, payload.get('params'))
    if behavior == 'wrong_height' and method == 'eth_getBlockByNumber' and isinstance(result, dict):
        number: object = None
        for key, value in result.items():
            if key == 'number':
                number = value
                break
        if isinstance(number, str):
            wrong_height = int(number, 16) + 1
            result = result | {'number': hex(wrong_height), 'hash': f'0x{wrong_height:064x}'}
    response_payload = {'jsonrpc': '2.0', 'id': request_id, 'result': result}
    return await _json_reply(ticket, response_payload)


@app.api_route('/run/{token}/http/{behavior}/tron/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE'])
async def tron_http(token: str, behavior: str, path: str, request: Request):
    if not _token_matches(token):
        return PlainTextResponse('Not found', status_code=404)
    peer = await _record_peer(request)
    await _record('http', behavior, 'tron', path, request.method)
    request_payload = {'method': request.method, 'path': path}
    ticket = await _begin_ledger(
        peer=peer,
        transport='http',
        behavior=behavior,
        chain='tron',
        source=0,
        method=path,
        request_id=None,
        request_payload=request_payload,
        params=None,
    )
    if behavior == 'unavailable':
        return await _plain_reply(ticket, b'upstream unavailable', 503)
    if behavior == 'rate_limit_date':
        retry_at = format_datetime(datetime.now(UTC) + timedelta(seconds=5), usegmt=True)
        return await _plain_reply(ticket, b'upstream rate limited', 429, headers={'Retry-After': retry_at})
    if behavior != 'good':
        return await _plain_reply(ticket, b'Not found', 404)
    if path.startswith('wallet/getnowblock'):
        response_payload = {'block_header': {'raw_data': {'number': _HEIGHTS['tron']}}, 'source': 'mock'}
        return await _json_reply(ticket, response_payload)
    return await _json_reply(ticket, {'Success': True, 'path': path, 'source': 'mock'})


def main() -> None:
    uvicorn.run(app, host='0.0.0.0', port=18080, log_config=None, access_log=False)


if __name__ == '__main__':
    main()
