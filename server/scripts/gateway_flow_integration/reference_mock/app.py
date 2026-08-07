import asyncio
import hmac
import os

import orjson
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from scripts.gateway_flow_integration.reference_mock.ledger import RequestLedger
from scripts.gateway_flow_integration.reference_mock.model import (
    EVM_CHAINS,
    UTXO_CHAINS,
    JsonValue,
    ReferenceBehavior,
    ReferenceChain,
    ReferenceReply,
    ReferenceTransport,
    RequestFacts,
    UnsupportedReferenceRequestError,
)
from scripts.gateway_flow_integration.reference_mock.replies import build_reply
from scripts.gateway_flow_integration.reference_mock.state import HeadBook

_JSON_HEAD_METHODS = frozenset({'eth_blockNumber', 'getblockchaininfo', 'getSlot'})
_TRON_HEAD_PATH = 'wallet/getnodeinfo'


def _parse_json(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_parse_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _parse_json(item) for key, item in value.items()}
    raise ValueError('Reference request contains an unsupported JSON value.')


def _json_height(chain: ReferenceChain, method: str, params: JsonValue, head: int) -> int:
    if method in _JSON_HEAD_METHODS:
        return head
    if not isinstance(params, list) or not params:
        raise UnsupportedReferenceRequestError(f'Reference method requires a height parameter: {method}.')
    raw = params[0]
    if chain in EVM_CHAINS:
        if not isinstance(raw, str):
            raise UnsupportedReferenceRequestError('EVM reference height must be hexadecimal.')
        try:
            return int(raw, 16)
        except ValueError as exc:
            raise UnsupportedReferenceRequestError('EVM reference height must be hexadecimal.') from exc
    if chain in UTXO_CHAINS and method == 'getblockhash':
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise UnsupportedReferenceRequestError('UTXO reference height must be an integer.')
        return raw
    if chain in UTXO_CHAINS and method == 'getblock':
        if not isinstance(raw, str):
            raise UnsupportedReferenceRequestError('UTXO reference hash must be a string.')
        try:
            return int(raw, 16)
        except ValueError as exc:
            raise UnsupportedReferenceRequestError('UTXO reference hash must encode a height.') from exc
    if chain is ReferenceChain.SOLANA and method == 'getBlock':
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise UnsupportedReferenceRequestError('Solana reference slot must be an integer.')
        return raw
    raise UnsupportedReferenceRequestError(f'Unsupported reference method: {method}.')


def _http_height(path: str, body: JsonValue, head: int) -> int:
    if path == _TRON_HEAD_PATH:
        return head
    if not isinstance(body, dict):
        raise UnsupportedReferenceRequestError(f'TRON reference path requires an object body: {path}.')
    key = 'num' if path == 'wallet/getblockbynum' else 'value'
    value = body.get(key)
    if path == 'wallet/gettransactioninfobyid' and isinstance(value, str):
        try:
            return int(value, 16)
        except ValueError as exc:
            raise UnsupportedReferenceRequestError('TRON transaction id must encode a height.') from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnsupportedReferenceRequestError(f'TRON reference path requires integer field {key}.')
    return value


def _response(reply: ReferenceReply) -> Response:
    return Response(content=reply.body, status_code=reply.status_code, media_type=reply.media_type)


def _error_reply(request_id: str | int | None, code: int, message: str) -> ReferenceReply:
    payload: JsonValue = {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}}
    return ReferenceReply(
        status_code=200,
        body=orjson.dumps(payload),
        media_type='application/json',
        response_id=request_id,
        payload=payload,
    )


def create_reference_app(
    token: str,
    *,
    timeout_seconds: float = 11.5,
    response_delay_seconds: float = 0.1,
    head_step: int = 0,
) -> FastAPI:
    """Create one isolated stateful upstream with a monotonic head and auditable fault behavior."""
    if not token:
        raise ValueError('Reference mock token is required.')
    if timeout_seconds <= 0:
        raise ValueError('Reference timeout must be positive.')
    if response_delay_seconds <= 0:
        raise ValueError('Reference response delay must be positive.')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    heads = HeadBook(step=head_step)
    ledger = RequestLedger()

    def token_matches(value: str) -> bool:
        return hmac.compare_digest(value, token)

    async def send_reference(
        facts: RequestFacts,
        behavior: ReferenceBehavior,
    ) -> Response:
        ticket = await ledger.begin(facts, behavior)
        try:
            if behavior is ReferenceBehavior.TIMEOUT:
                await asyncio.sleep(timeout_seconds)
            else:
                # The deterministic delay makes overlap observable without changing response semantics.
                await asyncio.sleep(response_delay_seconds)
            reply = build_reply(facts, behavior)
        except asyncio.CancelledError:
            canceled = ReferenceReply(
                status_code=499,
                body=b'reference request canceled',
                media_type='text/plain',
                response_id=None,
                payload=None,
            )
            await asyncio.shield(ledger.finish(ticket, facts, behavior, canceled))
            raise
        await ledger.finish(ticket, facts, behavior, reply)
        return _response(reply)

    @app.get('/__reference/health')
    async def health() -> dict[str, bool]:
        return {'ok': True}

    @app.get('/run/{access_token}/reference/state')
    async def state(access_token: str) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        return JSONResponse(await heads.snapshot())

    @app.post('/run/{access_token}/reference/advance/{chain_name}/{delta}')
    async def advance(access_token: str, chain_name: str, delta: int) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        try:
            chain = ReferenceChain(chain_name)
            height = await heads.advance(chain, delta)
        except ValueError as exc:
            return JSONResponse({'error': str(exc)}, status_code=400)
        return JSONResponse({'chain': chain.value, 'head': height})

    @app.get('/run/{access_token}/reference/ledger')
    async def ledger_report(access_token: str) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        return JSONResponse(await ledger.report())

    @app.delete('/run/{access_token}/reference/ledger')
    async def clear_ledger(access_token: str) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        try:
            await ledger.clear()
        except RuntimeError as exc:
            return JSONResponse({'error': str(exc)}, status_code=409)
        return JSONResponse({'cleared': True})

    @app.post('/run/{access_token}/reference/reset')
    async def reset(access_token: str) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        try:
            await ledger.clear()
        except RuntimeError as exc:
            return JSONResponse({'error': str(exc)}, status_code=409)
        reset_heads = await heads.reset()
        return JSONResponse({'heads': reset_heads, 'ledger_cleared': True})

    @app.post('/run/{access_token}/reference/jsonrpc/{behavior_name}/{chain_name}/{source}')
    async def jsonrpc(
        access_token: str,
        behavior_name: str,
        chain_name: str,
        source: int,
        request: Request,
    ) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        try:
            behavior = ReferenceBehavior(behavior_name)
            chain = ReferenceChain(chain_name)
            raw = await request.json()
            if not isinstance(raw, dict):
                raise ValueError('Reference JSON-RPC body must be an object.')
            method = raw.get('method')
            if not isinstance(method, str):
                raise ValueError('Reference JSON-RPC method must be a string.')
            request_id_raw = raw.get('id')
            request_id = (
                request_id_raw if isinstance(request_id_raw, str | int) and not isinstance(request_id_raw, bool) else None
            )
            params = _parse_json(raw.get('params', []))
            head = await heads.read(chain, tick=method in _JSON_HEAD_METHODS)
            target_height = _json_height(chain, method, params, head)
            facts = RequestFacts(
                transport=ReferenceTransport.JSONRPC,
                chain=chain,
                source=source,
                host=request.headers.get('host'),
                peer_host=request.client.host if request.client is not None else None,
                method=method,
                request_id=request_id,
                params=params,
                head=head,
                target_height=target_height,
            )
        except (ValueError, UnsupportedReferenceRequestError) as exc:
            return _response(_error_reply(None, -32600, str(exc)))
        return await send_reference(facts, behavior)

    @app.api_route(
        '/run/{access_token}/reference/http/{behavior_name}/tron/{source}/{path:path}',
        methods=['GET', 'POST'],
    )
    async def tron_http(
        access_token: str,
        behavior_name: str,
        source: int,
        path: str,
        request: Request,
    ) -> Response:
        if not token_matches(access_token):
            return PlainTextResponse('Not found', status_code=404)
        try:
            behavior = ReferenceBehavior(behavior_name)
            raw_body = await request.body()
            body = _parse_json(orjson.loads(raw_body)) if raw_body else {}
            head = await heads.read(ReferenceChain.TRON, tick=path == _TRON_HEAD_PATH)
            target_height = _http_height(path, body, head)
            facts = RequestFacts(
                transport=ReferenceTransport.HTTP_API,
                chain=ReferenceChain.TRON,
                source=source,
                host=request.headers.get('host'),
                peer_host=request.client.host if request.client is not None else None,
                method=path,
                request_id=None,
                params=body,
                head=head,
                target_height=target_height,
            )
        except (ValueError, UnsupportedReferenceRequestError, orjson.JSONDecodeError) as exc:
            return JSONResponse({'Error': str(exc)}, status_code=400)
        return await send_reference(facts, behavior)

    return app


def main() -> None:
    token = os.environ.get('INTEGRATION_RUN_TOKEN', '').strip()
    port = int(os.environ.get('INTEGRATION_REFERENCE_MOCK_PORT', '18081'))
    timeout_seconds = float(os.environ.get('INTEGRATION_REFERENCE_TIMEOUT_SECONDS', '11.5'))
    head_step = int(os.environ.get('INTEGRATION_REFERENCE_HEAD_STEP', '0'))
    app = create_reference_app(token, timeout_seconds=timeout_seconds, head_step=head_step)
    uvicorn.run(app, host='0.0.0.0', port=port, log_config=None, access_log=False)


if __name__ == '__main__':
    main()
