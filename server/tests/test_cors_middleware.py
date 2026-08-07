from collections.abc import AsyncGenerator

import pytest
from app import init_app
from app.services.public.jsonrpc.manager import RPC_CACHE_HIT_HEADER
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
from tests.helpers import asgi_client


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        # Reason: FastAPI accepts middleware classes at runtime; ty narrows this generic too much.
        CORSMiddleware,  # ty: ignore[invalid-argument-type]
        allow_origins=['https://example.com'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.get('/ping')
    async def ping():
        return {'msg': 'pong'}

    return app


def test_app_exposes_cache_hit_header() -> None:
    app = init_app()
    cors = next(middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware)
    exposed_headers = cors.kwargs['expose_headers']

    assert isinstance(exposed_headers, list)
    assert RPC_CACHE_HIT_HEADER in exposed_headers


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    app = _make_app()
    async with asgi_client(app) as c:
        yield c


@pytest.mark.anyio
async def test_cors_allowed_origin(client: AsyncClient) -> None:
    response = await client.get('/ping', headers={'origin': 'https://example.com'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://example.com'
    assert response.headers['access-control-allow-credentials'] == 'true'


@pytest.mark.anyio
async def test_cors_disallowed_origin(client: AsyncClient) -> None:
    response = await client.get('/ping', headers={'origin': 'https://evil.com'})
    assert response.status_code == 200
    assert 'access-control-allow-origin' not in response.headers


@pytest.mark.anyio
async def test_cors_preflight(client: AsyncClient) -> None:
    response = await client.options(
        '/ping',
        headers={
            'origin': 'https://example.com',
            'access-control-request-method': 'POST',
        },
    )
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://example.com'
    assert 'POST' in response.headers['access-control-allow-methods']
