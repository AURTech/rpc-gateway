import pytest
from app.core import context
from app.middleware.client_context import ClientContextMiddleware
from app.middleware.logging.request_log import RequestLogMiddleware
from fastapi import FastAPI, Request
from starlette.types import Message, Receive, Scope, Send
from tests.helpers import asgi_client


@pytest.mark.anyio
async def test_get_client_context_ignores_external_forwarding_headers() -> None:
    app = FastAPI()

    @app.get('/context')
    async def read_context(request: Request):
        return {'ip': context.client_ip(request), 'country': context.country(request)}

    async with asgi_client(app) as client:
        response = await client.get(
            '/context',
            headers={
                'CF-Connecting-IP': '203.0.113.10',
                'CF-IPCountry': 'SG',
                'X-Forwarded-For': '198.51.100.10, 198.51.100.11',
            },
        )

    assert response.status_code == 200
    assert response.json() == {'ip': '127.0.0.1', 'country': None}


@pytest.mark.parametrize('real_ip', ['203.0.113.10', '2001:db8::10'])
@pytest.mark.anyio
async def test_get_client_context_uses_proxy_real_ip(real_ip: str) -> None:
    app = FastAPI()

    @app.get('/context')
    async def read_context(request: Request):
        return {'ip': context.client_ip(request), 'country': context.country(request)}

    async with asgi_client(app) as client:
        response = await client.get('/context', headers={'X-Real-IP': real_ip, 'CF-IPCountry': 'SG'})

    assert response.status_code == 200
    assert response.json() == {'ip': real_ip, 'country': 'SG'}


@pytest.mark.anyio
async def test_get_client_context_rejects_appended_real_ip_chain() -> None:
    app = FastAPI()

    @app.get('/context')
    async def read_context(request: Request):
        return {'ip': context.client_ip(request), 'country': context.country(request)}

    async with asgi_client(app) as client:
        response = await client.get(
            '/context',
            headers={'X-Real-IP': '203.0.113.10, 198.51.100.20', 'CF-IPCountry': 'SG'},
        )

    assert response.status_code == 200
    assert response.json() == {'ip': '127.0.0.1', 'country': None}


@pytest.mark.anyio
async def test_get_client_context_rejects_duplicate_real_ip_headers() -> None:
    app = FastAPI()

    @app.get('/context')
    async def read_context(request: Request):
        return {'ip': context.client_ip(request), 'country': context.country(request)}

    headers = [
        ('X-Real-IP', '203.0.113.10'),
        ('X-Real-IP', '198.51.100.20'),
        ('CF-IPCountry', 'SG'),
    ]

    async with asgi_client(app) as client:
        response = await client.get('/context', headers=headers)

    assert response.status_code == 200
    assert response.json() == {'ip': '127.0.0.1', 'country': None}


@pytest.mark.parametrize('real_ip', ['not-an-ip', '   '])
@pytest.mark.anyio
async def test_get_client_context_falls_back_when_real_ip_is_invalid(real_ip: str) -> None:
    app = FastAPI()

    @app.get('/context')
    async def read_context(request: Request):
        return {'ip': context.client_ip(request), 'country': context.country(request)}

    async with asgi_client(app) as client:
        response = await client.get('/context', headers={'X-Real-IP': real_ip, 'CF-IPCountry': 'SG'})

    assert response.status_code == 200
    assert response.json() == {'ip': '127.0.0.1', 'country': None}


@pytest.mark.anyio
async def test_get_client_context_falls_back_to_request_client() -> None:
    app = FastAPI()

    @app.get('/context')
    async def read_context(request: Request):
        return {'ip': context.client_ip(request), 'country': context.country(request)}

    async with asgi_client(app) as client:
        response = await client.get('/context')

    assert response.status_code == 200
    assert response.json() == {'ip': '127.0.0.1', 'country': None}


@pytest.mark.anyio
@pytest.mark.parametrize('scope_type', ['websocket', 'lifespan'])
async def test_context_and_log_middleware_pass_through_non_http_scope(scope_type: str) -> None:
    received: tuple[Scope, Receive, Send] | None = None

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal received
        received = (scope, receive, send)

    async def receive() -> Message:
        return {'type': f'{scope_type}.disconnect'}

    async def send(_message: Message) -> None:
        return None

    scope: Scope = {'type': scope_type}
    middleware = ClientContextMiddleware(RequestLogMiddleware(application))
    await middleware(scope, receive, send)

    assert received == (scope, receive, send)
