import asyncio

import pytest
from app.core.exception import register_exception_handlers
from app.infra.redis import build_pattern
from app.middleware.limiter import RedisRateLimiter, RedisWebSocketRateLimiter
from app.middleware.limiter.redis_window import RedisSlidingWindowStore
from fastapi import Depends, FastAPI
from pyrate_limiter import Duration, Rate
from redis.asyncio import Redis
from starlette.datastructures import Headers
from tests.helpers import asgi_client


def _make_app(redis, *, rates: list[Rate] | None = None, bucket_key: str = 'test-limit') -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.redis = redis

    limiter = RedisRateLimiter(
        rates=rates or [Rate(2, Duration.SECOND * 60)],
        bucket_key=bucket_key,
    )

    @app.get('/ping', dependencies=[Depends(limiter)])
    async def ping():
        return {'msg': 'pong'}

    return app


def test_redis_sliding_window_scope_keys_are_unambiguous() -> None:
    store = RedisSlidingWindowStore([Rate(1, Duration.MINUTE)], 'test-scope-key')

    first = store.build_scope_key(('a', 'bc'))
    second = store.build_scope_key(('ab', 'c'))

    assert first != second
    assert len(first.rsplit(':', maxsplit=1)[1]) == 64
    assert len(second.rsplit(':', maxsplit=1)[1]) == 64


@pytest.mark.anyio
async def test_redis_limiter_first_request_passes(test_redis: Redis) -> None:
    app = _make_app(test_redis)
    async with asgi_client(app) as c:
        resp = await c.get('/ping')
    assert resp.status_code == 200
    assert resp.json() == {'msg': 'pong'}


@pytest.mark.anyio
async def test_redis_limiter_exceeds_rate(test_redis: Redis) -> None:
    app = _make_app(test_redis, rates=[Rate(1, Duration.SECOND * 60)])
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
async def test_redis_limiter_shared_count_across_limiters(test_redis: Redis) -> None:
    """Recreating a limiter with the same Redis + bucket_key shares counting state."""
    bucket_key = 'test-shared'

    app1 = _make_app(test_redis, rates=[Rate(2, Duration.SECOND * 60)], bucket_key=bucket_key)
    async with asgi_client(app1) as c:
        assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 200

    app2 = _make_app(test_redis, rates=[Rate(2, Duration.SECOND * 60)], bucket_key=bucket_key)
    async with asgi_client(app2) as c:
        resp = await c.get('/ping')
        assert resp.status_code == 429, 'count should persist across limiter instances via Redis'


@pytest.mark.anyio
async def test_redis_limiter_different_keys_independent(test_redis: Redis) -> None:
    """Different bucket keys maintain independent counters."""
    app_a = _make_app(test_redis, rates=[Rate(1, Duration.SECOND * 60)], bucket_key='test-a')
    async with asgi_client(app_a) as c:
        assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 429

    app_b = _make_app(test_redis, rates=[Rate(1, Duration.SECOND * 60)], bucket_key='test-b')
    async with asgi_client(app_b) as c:
        assert (await c.get('/ping')).status_code == 200


@pytest.mark.anyio
async def test_redis_limiter_different_scopes_independent(test_redis: Redis) -> None:
    app = _make_app(test_redis, rates=[Rate(1, Duration.SECOND * 60)])
    first_ip = {'X-Real-IP': '203.0.113.1'}
    second_ip = {'X-Real-IP': '203.0.113.2'}

    async with asgi_client(app) as c:
        assert (await c.get('/ping', headers=first_ip)).status_code == 200
        assert (await c.get('/ping', headers=first_ip)).status_code == 429
        assert (await c.get('/ping', headers=second_ip)).status_code == 200


@pytest.mark.anyio
async def test_redis_limiter_concurrent_scope_enforces_exact_limit(test_redis: Redis) -> None:
    app = _make_app(test_redis, rates=[Rate(17, Duration.SECOND * 60)])
    async with asgi_client(app) as c:
        responses = await asyncio.gather(*(c.get('/ping') for _ in range(100)))

    assert sum(response.status_code == 200 for response in responses) == 17
    assert sum(response.status_code == 429 for response in responses) == 83


@pytest.mark.anyio
async def test_redis_limiter_scope_key_is_opaque_and_expires(test_redis: Redis) -> None:
    app = _make_app(test_redis, rates=[Rate(1, Duration.SECOND * 60)], bucket_key='test-opaque')
    raw_ip = '203.0.113.9'
    async with asgi_client(app) as c:
        assert (await c.get('/ping', headers={'X-Real-IP': raw_ip})).status_code == 200

    pattern = build_pattern('rate-limit', 'v2', 'test-opaque', '*')
    keys = [str(key) async for key in test_redis.scan_iter(match=pattern)]
    assert len(keys) == 1
    assert raw_ip not in keys[0]
    ttl_ms = await test_redis.pttl(keys[0])
    assert 0 < ttl_ms <= 61_000


@pytest.mark.anyio
async def test_redis_limiter_scope_recovers_after_window(test_redis: Redis) -> None:
    app = _make_app(test_redis, rates=[Rate(1, Duration.SECOND)], bucket_key='test-recovery')
    async with asgi_client(app) as c:
        assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 429
        await asyncio.sleep(1.05)
        assert (await c.get('/ping')).status_code == 200


@pytest.mark.anyio
async def test_redis_limiter_enforces_every_window(test_redis: Redis) -> None:
    store = RedisSlidingWindowStore(
        [Rate(2, Duration.SECOND), Rate(3, Duration.MINUTE)],
        'test-multiple-windows',
    )
    scope = ('identity',)

    assert (await store.acquire(test_redis, scope)).allowed
    assert (await store.acquire(test_redis, scope)).allowed
    await asyncio.sleep(1.05)
    assert (await store.acquire(test_redis, scope)).allowed
    assert not (await store.acquire(test_redis, scope)).allowed


@pytest.mark.anyio
async def test_redis_limiter_within_limit(test_redis: Redis) -> None:
    app = _make_app(test_redis, rates=[Rate(3, Duration.SECOND * 60)])
    async with asgi_client(app) as c:
        for _ in range(3):
            assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 429


@pytest.mark.anyio
async def test_redis_limiter_skip_bypasses_redis_lookup(test_redis: Redis) -> None:
    async def skip_ping(request) -> bool:
        return request.scope['path'] == '/ping'

    app = FastAPI()
    app.state.redis = test_redis
    limiter = RedisRateLimiter(
        rates=[Rate(1, Duration.SECOND * 60)],
        bucket_key='test-skip',
        skip=skip_ping,
    )

    @app.get('/ping', dependencies=[Depends(limiter)])
    async def ping():
        return {'msg': 'pong'}

    async with asgi_client(app) as c:
        assert (await c.get('/ping')).status_code == 200
        assert (await c.get('/ping')).status_code == 200

    pattern = build_pattern('rate-limit', 'v2', 'test-skip', '*')
    assert [key async for key in test_redis.scan_iter(match=pattern)] == []


@pytest.mark.anyio
async def test_redis_websocket_limiter_uses_context_key_and_callback(test_redis: Redis) -> None:
    callback_calls = 0

    class FakeClient:
        host = '127.0.0.1'

    class FakeState:
        def __init__(self, redis) -> None:
            self.redis = redis

    class FakeApp:
        def __init__(self, redis) -> None:
            self.state = FakeState(redis)

    class FakeWebSocket:
        headers = Headers()
        client = FakeClient()
        scope = {'path': '/ws'}

        def __init__(self) -> None:
            self.app = FakeApp(test_redis)

    async def callback(ws: FakeWebSocket) -> str:
        nonlocal callback_calls
        callback_calls += 1
        return ws.scope['path']

    limiter = RedisWebSocketRateLimiter(
        rates=[Rate(1, Duration.SECOND * 60)],
        bucket_key='test-ws',
        callback=callback,
    )
    ws = FakeWebSocket()

    # Reason: FakeWebSocket carries only fields used by this limiter.
    assert await limiter(ws, context_key='room-a') is None  # type: ignore[arg-type]
    # Reason: FakeWebSocket carries only fields used by this limiter.
    assert await limiter(ws, context_key='room-b') is None  # type: ignore[arg-type]
    # Reason: FakeWebSocket carries only fields used by this limiter.
    assert await limiter(ws, context_key='room-a') == '/ws'  # type: ignore[arg-type]
    assert callback_calls == 1
