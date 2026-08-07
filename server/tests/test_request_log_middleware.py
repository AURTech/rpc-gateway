import asyncio
import re
from contextlib import contextmanager

import pytest
from app.core.trace import TRACE_ID_HEADER, TRACE_ID_SIZE
from app.middleware.client_context import ClientContextMiddleware
from app.middleware.logging import request_log
from app.middleware.logging.request_log import RequestLogMiddleware
from app.middleware.request_body_limit import RequestBodyLimitMiddleware
from fastapi import FastAPI, Request, Response
from starlette.responses import StreamingResponse
from starlette.types import Message, Receive, Scope, Send
from tests.helpers import asgi_client


def _http_scope(
    *,
    path: str = '/rpc-secret-value',
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Scope:
    return {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'http_version': '1.1',
        'method': 'POST',
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode(),
        'query_string': b'',
        'root_path': '',
        'headers': headers or [],
        'client': ('127.0.0.1', 1),
        'server': ('test', 80),
    }


class CapturingLog:
    def __init__(self) -> None:
        self.action: str | None = None
        self.trace_ids: list[str | None] = []
        self.messages: list[tuple[str, str | None, str]] = []

    def bind(self, **kwargs: str):
        self.action = kwargs.get('action')
        return self

    @contextmanager
    def contextualize(self, trace_id: str | None = None):
        self.trace_ids.append(trace_id)
        yield

    def info(self, message: str) -> None:
        self.messages.append(('info', self.action, message))

    def error(self, message: str) -> None:
        self.messages.append(('error', self.action, message))


@pytest.mark.anyio
async def test_request_log_middleware_prints_request_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    @application.get('/ping')
    async def ping(request: Request):
        request.state.connect_ip = '203.0.113.10'
        request.state.country = 'CN'
        return {'ok': True}

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/ping')

    assert response.status_code == 200
    assert len(log.messages) == 1
    assert len(log.trace_ids) == 1
    assert response.headers[TRACE_ID_HEADER] == log.trace_ids[0]
    assert len(response.headers[TRACE_ID_HEADER]) == TRACE_ID_SIZE
    level, action, message = log.messages[0]
    assert level == 'info'
    assert action == 'http'
    assert re.fullmatch(r'GET /ping 200 \d+(\.\d+)?ms 203\.0\.113\.10 CN', message)


@pytest.mark.anyio
async def test_request_log_middleware_prints_real_ip_client_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        ClientContextMiddleware  # ty: ignore[invalid-argument-type]
    )

    @application.get('/ping')
    async def ping():
        return {'ok': True}

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/ping', headers={'X-Real-IP': '203.0.113.20', 'CF-IPCountry': 'SG'})

    assert response.status_code == 200
    assert len(log.messages) == 1
    assert len(log.trace_ids) == 1
    assert response.headers[TRACE_ID_HEADER] == log.trace_ids[0]
    level, action, message = log.messages[0]
    assert level == 'info'
    assert action == 'http'
    assert re.fullmatch(r'GET /ping 200 \d+(\.\d+)?ms 203\.0\.113\.20 SG', message)


@pytest.mark.anyio
@pytest.mark.parametrize('status_code', [403, 500])
async def test_request_log_middleware_logs_403_and_5xx_as_errors(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    @application.get('/status')
    async def status():
        return Response(status_code=status_code)

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/status')

    assert response.status_code == status_code
    assert len(log.messages) == 1
    assert len(log.trace_ids) == 1
    assert response.headers[TRACE_ID_HEADER] == log.trace_ids[0]
    level, action, message = log.messages[0]
    assert level == 'error'
    assert action == 'http'
    assert re.fullmatch(rf'GET /status {status_code} \d+(\.\d+)?ms - -', message)


@pytest.mark.anyio
async def test_request_log_middleware_uses_inbound_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    seen_trace_ids = []
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    @application.get('/ping')
    async def ping(request: Request):
        seen_trace_ids.append(request.state.trace_id)
        return {'ok': True}

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/ping', headers={TRACE_ID_HEADER: 'ExternalTrace123'})

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER] == 'ExternalTrace123'
    assert log.trace_ids == ['ExternalTrace123']
    assert seen_trace_ids == ['ExternalTrace123']


@pytest.mark.anyio
async def test_request_log_middleware_replaces_invalid_inbound_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    @application.get('/ping')
    async def ping():
        return {'ok': True}

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/ping', headers={TRACE_ID_HEADER: 'bad trace | value'})

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER] != 'bad trace | value'
    assert response.headers[TRACE_ID_HEADER] == log.trace_ids[0]
    assert len(response.headers[TRACE_ID_HEADER]) == TRACE_ID_SIZE


@pytest.mark.anyio
async def test_request_log_middleware_uses_route_template(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    @application.get('/items/{item_id}')
    async def item(item_id: str):
        return {'id': item_id}

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/items/sensitive-value')

    assert response.status_code == 200
    assert re.fullmatch(r'GET /items/\{item_id\} 200 \d+(\.\d+)?ms - -', log.messages[0][2])
    assert 'sensitive-value' not in log.messages[0][2]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('route_path', 'request_path', 'host'),
    [
        ('/{path_key}', '/rpc-secret-value', 'ether-jsonrpc.example.test'),
        (
            '/{path_key}/{service}/{method}',
            '/rpc-secret-value/wallet/getnowblock',
            'tron-httpapi.example.test',
        ),
    ],
)
async def test_request_log_middleware_redacts_matched_rpc_path_key(
    monkeypatch: pytest.MonkeyPatch,
    route_path: str,
    request_path: str,
    host: str,
) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    application.add_api_route(route_path, lambda: {'ok': True}, methods=['POST'])

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.post(request_path, headers={'Host': host})

    assert response.status_code == 200
    assert route_path in log.messages[0][2]
    assert 'rpc-secret-value' not in log.messages[0][2]


@pytest.mark.anyio
async def test_request_log_middleware_keeps_unmatched_control_path(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    application = FastAPI()
    application.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )

    monkeypatch.setattr(request_log, 'log', log)
    async with asgi_client(application) as client:
        response = await client.get('/ordinary/missing', headers={'Host': 'console.example.test'})

    assert response.status_code == 404
    assert '/ordinary/missing' in log.messages[0][2]


@pytest.mark.anyio
async def test_request_log_middleware_logs_disconnect_before_body(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    called = False
    sent: list[Message] = []

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    async def receive() -> Message:
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)

    monkeypatch.setattr(request_log, 'log', log)
    monkeypatch.setattr(request_log, 'is_gateway_host', lambda _host: True)
    scope = _http_scope(
        headers=[
            (b'host', b'ether-jsonrpc.example.test'),
            (b'x-real-ip', b'203.0.113.20'),
            (b'cf-ipcountry', b'SG'),
        ]
    )
    middleware = ClientContextMiddleware(RequestLogMiddleware(RequestBodyLimitMiddleware(application, max_bytes=16)))
    await middleware(scope, receive, send)

    assert called is False
    assert sent == []
    assert len(log.messages) == 1
    level, action, message = log.messages[0]
    assert level == 'info'
    assert action == 'http'
    assert re.fullmatch(r'POST /\{api_key\} disconnected \d+(\.\d+)?ms 203\.0\.113\.20 SG', message)
    assert 'rpc-secret-value' not in message


@pytest.mark.anyio
async def test_request_log_middleware_logs_stream_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()
    first_chunk = asyncio.Event()
    stream_cleaned = asyncio.Event()
    receive_calls = 0
    sent: list[Message] = []

    async def stream():
        try:
            yield b'first'
            first_chunk.set()
            await asyncio.Event().wait()
        finally:
            stream_cleaned.set()

    response = StreamingResponse(stream())

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        await response(scope, receive, send)

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await first_chunk.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)

    monkeypatch.setattr(request_log, 'log', log)
    middleware = RequestLogMiddleware(RequestBodyLimitMiddleware(application, max_bytes=4))
    await middleware(_http_scope(path='/stream'), receive, send)

    assert sent[0]['type'] == 'http.response.start'
    assert not any(message['type'] == 'http.response.body' and not message.get('more_body', False) for message in sent)
    assert stream_cleaned.is_set()
    assert len(log.messages) == 1
    assert re.fullmatch(r'POST /stream disconnected \d+(\.\d+)?ms - -', log.messages[0][2])


@pytest.mark.anyio
async def test_request_log_middleware_keeps_complete_response_during_disconnect_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = CapturingLog()
    disconnect_ready = asyncio.Event()
    receive_calls = 0
    sent: list[Message] = []

    async def application(_scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok', 'more_body': False})

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnect_ready.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)
        if message['type'] == 'http.response.body' and not message.get('more_body', False):
            disconnect_ready.set()

    monkeypatch.setattr(request_log, 'log', log)
    middleware = RequestLogMiddleware(RequestBodyLimitMiddleware(application, max_bytes=4))
    await middleware(_http_scope(path='/complete'), receive, send)

    response_headers = dict(sent[0]['headers'])
    trace_id = log.trace_ids[0]
    assert trace_id is not None
    assert response_headers[TRACE_ID_HEADER.lower().encode()] == trace_id.encode()
    assert re.fullmatch(r'POST /complete 200 \d+(\.\d+)?ms - -', log.messages[0][2])


@pytest.mark.anyio
async def test_request_log_middleware_raises_when_application_returns_without_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = CapturingLog()

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        return None

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(_message: Message) -> None:
        return None

    monkeypatch.setattr(request_log, 'log', log)
    middleware = RequestLogMiddleware(application)
    with pytest.raises(RuntimeError, match='HTTP application returned without starting a response'):
        await middleware(_http_scope(path='/empty'), receive, send)

    assert len(log.messages) == 1
    assert re.fullmatch(r'POST /empty 500 \d+(\.\d+)?ms - -', log.messages[0][2])


@pytest.mark.anyio
async def test_request_log_middleware_propagates_application_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise ValueError('handler failed')

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(_message: Message) -> None:
        return None

    monkeypatch.setattr(request_log, 'log', log)
    middleware = RequestLogMiddleware(application)
    with pytest.raises(ValueError, match='handler failed'):
        await middleware(_http_scope(path='/failure'), receive, send)

    assert len(log.messages) == 1
    assert re.fullmatch(r'POST /failure 500 \d+(\.\d+)?ms - -', log.messages[0][2])


@pytest.mark.anyio
async def test_request_log_middleware_prioritizes_exception_after_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()

    async def application(_scope: Scope, receive: Receive, _send: Send) -> None:
        message = await receive()
        assert message['type'] == 'http.disconnect'
        raise ValueError('handler failed')

    async def receive() -> Message:
        return {'type': 'http.disconnect'}

    async def send(_message: Message) -> None:
        return None

    monkeypatch.setattr(request_log, 'log', log)
    middleware = RequestLogMiddleware(application)
    with pytest.raises(ValueError, match='handler failed'):
        await middleware(_http_scope(path='/failure'), receive, send)

    assert len(log.messages) == 1
    assert re.fullmatch(r'POST /failure 500 \d+(\.\d+)?ms - -', log.messages[0][2])


@pytest.mark.anyio
async def test_request_log_middleware_treats_send_oserror_as_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    log = CapturingLog()

    async def application(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(_message: Message) -> None:
        raise OSError('connection closed')

    monkeypatch.setattr(request_log, 'log', log)
    middleware = RequestLogMiddleware(application)
    await middleware(_http_scope(path='/send'), receive, send)

    assert len(log.messages) == 1
    assert re.fullmatch(r'POST /send disconnected \d+(\.\d+)?ms - -', log.messages[0][2])
