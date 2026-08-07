from typing import ClassVar

from redis.asyncio import Redis


class _RedisAccessor:
    def __get__(self, instance: object, owner: type['Manager']) -> Redis:
        client = owner._redis
        if client is None:
            raise RuntimeError('Redis client has not been set.')
        return client


class Manager:
    _redis: ClassVar[Redis | None] = None
    redis = _RedisAccessor()

    @classmethod
    def set_redis(cls, client: Redis) -> None:
        cls._redis = client

    @classmethod
    def clear_redis(cls) -> None:
        cls._redis = None
