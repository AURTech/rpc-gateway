import asyncio
from typing import Any

from app.middleware.limiter.callback import default_callback
from app.middleware.limiter.identifier import default_identifier
from app.middleware.limiter.redis_window import RedisSlidingWindowStore
from pyrate_limiter import Limiter, Rate
from redis.asyncio import Redis
from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket


class _BaseRateLimiter:
    def __init__(
        self,
        limiter: Limiter,
        identifier=default_identifier,
        callback=default_callback,
        blocking: bool = False,
        skip=None,
    ):
        self.limiter = limiter
        self.identifier = identifier
        self.callback = callback
        self.blocking = blocking
        self.skip = skip


class RateLimiter(_BaseRateLimiter):
    async def __call__(self, request: Request, response: Response) -> Any:
        if self.skip and await self.skip(request):
            return
        rate_key = await self.identifier(request)
        success = await self.limiter.try_acquire_async(rate_key, blocking=self.blocking)
        if not success:
            return await self.callback(request, response)


class WebSocketRateLimiter(_BaseRateLimiter):
    async def __call__(self, ws: WebSocket, context_key: str = '') -> Any:
        if self.skip and await self.skip(ws):
            return
        rate_key = await self.identifier(ws)
        key = f'{rate_key}:{context_key}'
        success = await self.limiter.try_acquire_async(key, blocking=self.blocking)
        if not success:
            return await self.callback(ws)


# ------------------------------ Redis Backend ------------------------------


class _BaseRedisRateLimiter:
    """Redis-backed limiter with independent counters per scope.

    Counting state is persisted in Redis, shared across processes.
    """

    def __init__(
        self,
        rates: list[Rate],
        bucket_key: str,
        identifier=default_identifier,
        callback=default_callback,
        blocking: bool = False,
        skip=None,
    ):
        self.rates = rates
        self.bucket_key = bucket_key
        self.identifier = identifier
        self.callback = callback
        self.blocking = blocking
        self.skip = skip
        self._store = RedisSlidingWindowStore(rates, bucket_key)

    async def _try_acquire(self, redis_client: Redis, scope: tuple[str, ...]) -> bool:
        while True:
            result = await self._store.acquire(redis_client, scope)
            if result.allowed:
                return True
            if not self.blocking:
                return False
            await asyncio.sleep((result.retry_after_ms + 50) / 1000)


class RedisRateLimiter(_BaseRedisRateLimiter):
    async def __call__(self, request: Request, response: Response) -> Any:
        if self.skip and await self.skip(request):
            return
        rate_key = await self.identifier(request)
        return await self.acquire(request, response, rate_key)

    async def acquire(self, request: Request, response: Response, rate_key: str) -> Any:
        redis_client = request.app.state.redis
        success = await self._try_acquire(redis_client, (rate_key,))
        if not success:
            return await self.callback(request, response)


class RedisWebSocketRateLimiter(_BaseRedisRateLimiter):
    async def __call__(self, ws: WebSocket, context_key: str = '') -> Any:
        if self.skip and await self.skip(ws):
            return
        redis_client = ws.app.state.redis
        rate_key = await self.identifier(ws)
        success = await self._try_acquire(redis_client, (rate_key, context_key))
        if not success:
            return await self.callback(ws)
