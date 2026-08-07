from aiocache import caches
from aiocache.base import BaseCache
from redis.asyncio import ConnectionPool
from redis.asyncio.client import Redis
from redis.asyncio.connection import SSLConnection

_cache_timeout = 1


def _cache_config_from_url(redis_url: str, namespace: str) -> dict[str, object]:
    pool = ConnectionPool.from_url(redis_url)
    connection_kwargs = dict(pool.connection_kwargs)
    host = connection_kwargs.pop('host', None)
    port = int(connection_kwargs.pop('port', 6379))
    db = int(connection_kwargs.pop('db', 0))
    password = connection_kwargs.pop('password', None)
    ssl = issubclass(pool.connection_class, SSLConnection)

    if host is None:
        raise ValueError('REDIS_URL must use redis:// or rediss:// with a hostname')

    config: dict[str, object] = {
        'cache': 'aiocache.RedisCache',
        'endpoint': host,
        'port': port,
        'db': db,
        'password': password,
        'namespace': namespace,
        'timeout': _cache_timeout,
        'serializer': {
            'class': 'aiocache.serializers.JsonSerializer',
        },
    }
    if ssl:
        config['ssl'] = True
    if connection_kwargs:
        config['connection_pool_kwargs'] = connection_kwargs

    return config


def init_cache(redis_url: str, namespace: str) -> None:
    """Configure aiocache aliases from the canonical Redis URL."""
    caches.set_config(
        {
            'default': _cache_config_from_url(redis_url, namespace),
        }
    )


def get_cache(alias: str = 'default') -> BaseCache:
    # Reason: aiocache returns BaseCache for configured aliases; its public typing is broader.
    cache: BaseCache = caches.get(alias)  # type: ignore[assignment]
    return cache


async def close_cache() -> None:
    cache = get_cache()
    client = getattr(cache, 'client', None)
    if isinstance(client, Redis):
        await client.aclose()
        return

    await cache.close()
