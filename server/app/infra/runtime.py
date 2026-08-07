import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.core.config import CONF
from app.infra.http_client import build_shared_http_client


@dataclass(slots=True, kw_only=True)
class RuntimeClients:
    redis: Redis
    shared_http_client: httpx.AsyncClient


async def create_redis_client() -> Redis:
    """Create a Redis client and close it if startup validation fails.

    Raises:
        SystemError: Redis ping fails.
        Exception: Redis client creation or ping raises.
    """
    client = Redis.from_url(
        url=CONF.REDIS_URL,
        decode_responses=True,
        retry_on_timeout=False,
        socket_connect_timeout=CONF.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=CONF.REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        # Reason: redis.asyncio ping is awaitable at runtime; stubs are narrower here.
        if not await client.ping():  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            raise SystemError('Redis init error.')
        return client
    except Exception:
        with contextlib.suppress(Exception):
            await client.aclose()
        raise


@asynccontextmanager
async def open_runtime_clients() -> AsyncGenerator[RuntimeClients]:
    """Open Redis and HTTP clients as one runtime lifecycle.

    Side effects:
        Closes any successfully opened client when startup fails or the context exits.
    """
    async with contextlib.AsyncExitStack() as stack:
        redis = await create_redis_client()
        stack.push_async_callback(redis.aclose)
        shared_http_client = build_shared_http_client()
        stack.push_async_callback(shared_http_client.aclose)
        yield RuntimeClients(
            redis=redis,
            shared_http_client=shared_http_client,
        )
