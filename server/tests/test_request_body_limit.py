import asyncio

import anyio
import pytest
from app.middleware.request_body_limit import (
    INVALID_CONTENT_LENGTH_MESSAGE,
    REQUEST_BODY_READ_TIMEOUT_MESSAGE,
    REQUEST_BODY_TOO_LARGE_MESSAGE,
    RequestBodyLimitMiddleware,
)
from fastapi import FastAPI, Request
from starlette.types import Message, Receive, Scope, Send
from tests.helpers import asgi_client


def _http_scope(*, method: str = 'POST', headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'http_version': '1.1',
        'method': method,
        'scheme': 'http',
        'path': '/body',
        'raw_path': b'/body',
        'query_string': b'',
        'root_path': '',
        'headers': headers or [],
        'client': ('127.0.0.1', 1),
        'server': ('test', 80),
    }


@pytest.mark.anyio
async def test_request_body_limit_rejects_declared_size_before_handler() -> None:
    called = False
    application = FastAPI()
    # Reason: Starlette's type stub is narrower than its runtime middleware factory contract.
    application.add_middleware(RequestBodyLimitMiddleware, max_bytes=4)  # ty: ignore[invalid-argument-type]

    @application.post('/body')
    async def body() -> dict[str, bool]:
        nonlocal called
        called = True
        return {'called': True}

    async with asgi_client(application) as client:
        response = await client.post('/body', content=b'12345')

    assert response.status_code == 413
    error = response.json()
    assert error['success'] is False
    assert error['msg'] == REQUEST_BODY_TOO_LARGE_MESSAGE
    assert called is False


@pytest.mark.anyio
@pytest.mark.parametrize('method', ['GET', 'POST'])
async def test_request_body_limit_counts_chunked_body_before_handler(method: str) -> None:
    called = False

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    messages = iter(
        [
            {'type': 'http.request', 'body': b'123', 'more_body': True},
            {'type': 'http.request', 'body': b'45', 'more_body': False},
        ]
    )
    sent: list[Message] = []

    async def receive() -> Message:
        return next(messages)

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(_http_scope(method=method), receive, send)

    assert called is False
    assert [message['type'] for message in sent] == ['http.response.start', 'http.response.body']
    assert sent[0]['status'] == 413


@pytest.mark.anyio
@pytest.mark.parametrize('method', ['GET', 'POST'])
async def test_request_body_limit_accepts_exact_size(method: str) -> None:
    application = FastAPI()
    # Reason: Starlette's type stub is narrower than its runtime middleware factory contract.
    application.add_middleware(RequestBodyLimitMiddleware, max_bytes=4)  # ty: ignore[invalid-argument-type]

    @application.api_route('/body', methods=['GET', 'POST'])
    async def body(request: Request) -> dict[str, str]:
        return {'body': (await request.body()).decode()}

    async with asgi_client(application) as client:
        response = await client.request(method, '/body', content=b'1234')

    assert response.status_code == 200
    assert response.json() == {'body': '1234'}


@pytest.mark.anyio
@pytest.mark.parametrize(
    'headers',
    [
        [(b'content-length', b'-1')],
        [(b'content-length', b'not-a-number')],
        [(b'content-length', b'3'), (b'content-length', b'4')],
        [(b'content-length', b'3, 4')],
    ],
)
async def test_request_body_limit_rejects_invalid_content_length(headers: list[tuple[bytes, bytes]]) -> None:
    called = False

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    async def receive() -> Message:
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    await middleware(_http_scope(headers=headers), receive, send)

    assert called is False
    assert sent[0]['status'] == 400
    assert INVALID_CONTENT_LENGTH_MESSAGE.encode() in sent[1]['body']


@pytest.mark.anyio
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
async def test_request_body_limit_accepts_bodyless_method_without_delay(method: str) -> None:
    called = False
    receive_calls = 0
    replayed_body: bytes | None = None

    async def application(_scope: Scope, receive: Receive, _send: Send) -> None:
        nonlocal called, replayed_body
        called = True
        message = await receive()
        replayed_body = message.get('body', b'')

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(_message: Message) -> None:
        return None

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4, read_timeout_seconds=1)
    with anyio.fail_after(0.1):
        await middleware(_http_scope(method=method), receive, send)

    assert called is True
    assert receive_calls <= 2
    assert replayed_body == b''


@pytest.mark.anyio
async def test_request_body_limit_disconnects_without_response() -> None:
    called = False
    sent: list[Message] = []

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    async def receive() -> Message:
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    await middleware(_http_scope(), receive, send)

    assert called is False
    assert sent == []


@pytest.mark.anyio
async def test_request_body_limit_times_out_complete_body_deadline() -> None:
    called = False
    sent: list[Message] = []

    async def application(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4, read_timeout_seconds=0)
    await middleware(_http_scope(), receive, send)

    assert called is False
    assert sent[0]['status'] == 408
    assert REQUEST_BODY_READ_TIMEOUT_MESSAGE.encode() in sent[1]['body']


@pytest.mark.anyio
async def test_request_body_limit_cancels_handler_after_body_disconnect() -> None:
    handler_started = asyncio.Event()
    disconnect_ready = asyncio.Event()
    handler_cleaned = asyncio.Event()
    receive_calls = 0
    sent: list[Message] = []

    async def application(_scope: Scope, receive: Receive, _send: Send) -> None:
        message = await receive()
        assert message['body'] == b'payload'
        handler_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            handler_cleaned.set()

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'payload', 'more_body': False}
        await disconnect_ready.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(application, max_bytes=16)
    middleware_task = asyncio.create_task(middleware(_http_scope(), receive, send))
    await handler_started.wait()
    disconnect_ready.set()
    await middleware_task

    assert handler_cleaned.is_set()
    assert sent == []


@pytest.mark.anyio
async def test_request_body_limit_prioritizes_handler_error_during_disconnect_cleanup() -> None:
    handler_started = asyncio.Event()
    disconnect_ready = asyncio.Event()
    receive_calls = 0

    async def application(_scope: Scope, receive: Receive, _send: Send) -> None:
        await receive()
        handler_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            raise ValueError('cleanup failed') from exc

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnect_ready.wait()
        return {'type': 'http.disconnect'}

    async def send(_message: Message) -> None:
        return None

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    middleware_task = asyncio.create_task(middleware(_http_scope(), receive, send))
    await handler_started.wait()
    disconnect_ready.set()

    with pytest.raises(ValueError, match='cleanup failed'):
        await middleware_task


@pytest.mark.anyio
async def test_request_body_limit_propagates_external_cancellation() -> None:
    handler_started = asyncio.Event()
    handler_cleaned = asyncio.Event()
    receive_calls = 0

    async def application(_scope: Scope, receive: Receive, _send: Send) -> None:
        await receive()
        handler_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            handler_cleaned.set()

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(_message: Message) -> None:
        return None

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    middleware_task = asyncio.create_task(middleware(_http_scope(), receive, send))
    await handler_started.wait()
    middleware_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await middleware_task
    assert handler_cleaned.is_set()


@pytest.mark.anyio
async def test_request_body_limit_allows_background_work_after_complete_response() -> None:
    response_sent = asyncio.Event()
    finish_background = asyncio.Event()
    background_done = asyncio.Event()
    receive_calls = 0

    async def application(_scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok', 'more_body': False})
        try:
            await finish_background.wait()
        finally:
            background_done.set()

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.Event().wait()
        raise AssertionError('Unreachable receive result.')

    async def send(message: Message) -> None:
        if message['type'] == 'http.response.body' and not message.get('more_body', False):
            response_sent.set()

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    middleware_task = asyncio.create_task(middleware(_http_scope(), receive, send))
    await response_sent.wait()
    await asyncio.sleep(0)

    assert not middleware_task.done()
    assert not background_done.is_set()

    finish_background.set()
    await middleware_task
    assert background_done.is_set()


@pytest.mark.anyio
async def test_request_body_limit_forwards_post_response_disconnect() -> None:
    post_response_receive_started = asyncio.Event()
    disconnect_ready = asyncio.Event()
    received_messages: list[Message] = []
    receive_calls = 0

    async def application(_scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok', 'more_body': False})
        post_response_receive_started.set()
        received_messages.append(await receive())

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnect_ready.wait()
        return {'type': 'http.disconnect'}

    async def send(_message: Message) -> None:
        return None

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    middleware_task = asyncio.create_task(middleware(_http_scope(), receive, send))
    await post_response_receive_started.wait()
    await asyncio.sleep(0)
    disconnect_ready.set()

    with anyio.fail_after(1):
        await middleware_task

    assert received_messages == [{'type': 'http.disconnect'}]
    assert receive_calls == 2


@pytest.mark.anyio
async def test_request_body_limit_keeps_completed_response_when_disconnect_arrives() -> None:
    disconnect_ready = asyncio.Event()
    receive_calls = 0
    sent: list[Message] = []

    async def application(_scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({'type': 'http.response.start', 'status': 201, 'headers': []})
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

    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    await middleware(_http_scope(), receive, send)

    assert [message['type'] for message in sent] == ['http.response.start', 'http.response.body']
    assert sent[0]['status'] == 201


@pytest.mark.anyio
@pytest.mark.parametrize('scope_type', ['websocket', 'lifespan'])
async def test_request_body_limit_passes_through_non_http_scope(scope_type: str) -> None:
    received: tuple[Scope, Receive, Send] | None = None

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal received
        received = (scope, receive, send)

    async def receive() -> Message:
        return {'type': f'{scope_type}.disconnect'}

    async def send(_message: Message) -> None:
        return None

    scope: Scope = {'type': scope_type}
    middleware = RequestBodyLimitMiddleware(application, max_bytes=4)
    await middleware(scope, receive, send)

    assert received == (scope, receive, send)
