import pytest
from app.core.exception import register_exception_handlers
from app.middleware.limiter import RateLimiter, RateLimiterMiddleware, WebSocketRateLimiter
from app.middleware.limiter.identifier import default_identifier
from fastapi import FastAPI
from fastapi.params import Depends
from pyrate_limiter import Duration, Limiter, Rate
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse
from tests.helpers import asgi_client


def _make_app(*, rate: Rate | None = None, skip=None, callback=None) -> FastAPI:
    app = FastAPI()
    limiter = Limiter(rate or Rate(2, Duration.SECOND * 60))
    kwargs: dict = {'limiter': limiter}
    if skip is not None:
        kwargs['skip'] = skip
    if callback is not None:
        kwargs['callback'] = callback
    app.add_middleware(
        # Reason: FastAPI accepts middleware classes at runtime; ty narrows this generic too much.
        RateLimiterMiddleware,  # ty: ignore[invalid-argument-type]
        **kwargs,
    )

    @app.get('/ping')
    async def ping():
        return {'msg': 'pong'}

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    return app


@pytest.mark.anyio
async def test_first_request_passes() -> None:
    app = _make_app()
    async with asgi_client(app) as c:
        response = await c.get('/ping')
    assert response.status_code == 200
    assert response.json() == {'msg': 'pong'}


@pytest.mark.anyio
async def test_exceeds_rate_limit() -> None:
    app = _make_app(rate=Rate(1, Duration.SECOND * 60))
    async with asgi_client(app) as c:
        first = await c.get('/ping')
        assert first.status_code == 200

        second = await c.get('/ping')
        assert second.status_code == 429
        body = second.json()
        assert body['success'] is False
        assert body['msg'] == 'Request too fast, please try again later.'
        assert body['code'] == 'rate_limited'


@pytest.mark.anyio
async def test_skip_bypasses_limit() -> None:
    async def skip_health(request: Request) -> bool:
        return request.scope['path'] == '/health'

    app = _make_app(rate=Rate(1, Duration.SECOND * 60), skip=skip_health)
    async with asgi_client(app) as c:
        assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 429

        for _ in range(5):
            resp = await c.get('/health')
            assert resp.status_code == 200


@pytest.mark.anyio
async def test_default_identifier_uses_proxy_real_ip() -> None:
    app = FastAPI()

    @app.get('/identifier')
    async def identifier(request: Request):
        return {'key': await default_identifier(request)}

    async with asgi_client(app) as c:
        response = await c.get('/identifier', headers={'X-Real-IP': '203.0.113.1'})

    assert response.status_code == 200
    assert response.json() == {'key': '203.0.113.1:/identifier'}


@pytest.mark.anyio
async def test_custom_callback() -> None:
    async def custom_cb(request: Request):
        return JSONResponse(status_code=503, content={'error': 'rate limited'})

    app = _make_app(rate=Rate(1, Duration.SECOND * 60), callback=custom_cb)
    async with asgi_client(app) as c:
        assert (await c.get('/ping')).status_code == 200
        resp = await c.get('/ping')
        assert resp.status_code == 503
        assert resp.json() == {'error': 'rate limited'}


@pytest.mark.anyio
async def test_within_limit_multiple_requests() -> None:
    app = _make_app(rate=Rate(3, Duration.SECOND * 60))
    async with asgi_client(app) as c:
        for _ in range(3):
            assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 429


@pytest.mark.anyio
async def test_dependency_rate_limiter_exceeds_rate_limit() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    limiter = RateLimiter(limiter=Limiter(Rate(1, Duration.SECOND * 60)))

    @app.get('/limited', dependencies=[Depends(limiter)])
    async def limited():
        return {'msg': 'pong'}

    async with asgi_client(app) as c:
        assert (await c.get('/limited')).status_code == 200
        response = await c.get('/limited')

    assert response.status_code == 429
    body = response.json()
    assert body['success'] is False
    assert body['msg'] == 'Request too fast, please try again later.'
    assert body['code'] == 'rate_limited'


@pytest.mark.anyio
async def test_dependency_rate_limiter_skip_bypasses_limit() -> None:
    async def skip_limiter(request: Request) -> bool:
        return request.scope['path'] == '/limited'

    app = FastAPI()
    limiter = RateLimiter(limiter=Limiter(Rate(1, Duration.SECOND * 60)), skip=skip_limiter)

    @app.get('/limited', dependencies=[Depends(limiter)])
    async def limited():
        return {'msg': 'pong'}

    async with asgi_client(app) as c:
        assert (await c.get('/limited')).status_code == 200
        assert (await c.get('/limited')).status_code == 200


@pytest.mark.anyio
async def test_websocket_rate_limiter_uses_context_key_and_callback() -> None:
    callback_calls = 0

    class FakeLimiter:
        def __init__(self) -> None:
            self.keys: list[str] = []

        async def try_acquire_async(self, key: str, *, blocking: bool = False) -> bool:
            self.keys.append(key)
            return len(self.keys) == 1

    class FakeClient:
        host = '127.0.0.1'

    class FakeWebSocket:
        headers = Headers()
        client = FakeClient()
        scope = {'path': '/ws'}

    async def callback(ws: FakeWebSocket) -> str:
        nonlocal callback_calls
        callback_calls += 1
        return ws.scope['path']

    fake_limiter = FakeLimiter()
    limiter = WebSocketRateLimiter(
        # Reason: FakeLimiter implements the try_acquire_async subset used by WebSocketRateLimiter.
        limiter=fake_limiter,  # type: ignore[arg-type]
        callback=callback,
    )
    ws = FakeWebSocket()

    # Reason: FakeWebSocket carries only fields used by this limiter.
    assert await limiter(ws, context_key='room-a') is None  # type: ignore[arg-type]
    # Reason: FakeWebSocket carries only fields used by this limiter.
    assert await limiter(ws, context_key='room-b') == '/ws'  # type: ignore[arg-type]
    assert fake_limiter.keys == ['127.0.0.1:/ws:room-a', '127.0.0.1:/ws:room-b']
    assert callback_calls == 1


@pytest.mark.anyio
async def test_websocket_rate_limiter_skip_bypasses_limit() -> None:
    class FakeWebSocket:
        pass

    async def skip_limiter(ws: FakeWebSocket) -> bool:
        return True

    limiter = WebSocketRateLimiter(
        limiter=Limiter(Rate(1, Duration.SECOND * 60)),
        skip=skip_limiter,
    )

    # Reason: FakeWebSocket carries only fields used by this limiter.
    assert await limiter(FakeWebSocket()) is None  # type: ignore[arg-type]
