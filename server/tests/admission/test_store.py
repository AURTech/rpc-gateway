import asyncio

import pytest
from app.infra.redis import build_key
from app.services.admission import LocalTokenBucketStore, RedisTokenBucketStore, TokenBucketRequest
from redis.asyncio import Redis


def _bucket(key: str, *, burst: int = 1, rps: float = 0.001) -> TokenBucketRequest:
    redis_key = build_key('rate_limit_test', key.replace(':', '-'))
    return TokenBucketRequest(key=redis_key, rps=rps, burst=burst)


@pytest.mark.anyio
async def test_redis_burst_concurrency(test_redis: Redis) -> None:
    store = RedisTokenBucketStore(test_redis)
    bucket = _bucket('rate-limit:test:concurrent', burst=17)

    results = await asyncio.gather(*(store.acquire((bucket,), timeout_ms=1000) for _ in range(100)))

    assert sum(result.allowed for result in results) == 17
    assert all(not result.capacity_limited for result in results)


@pytest.mark.anyio
async def test_redis_instances_share_state(test_redis: Redis) -> None:
    first_store = RedisTokenBucketStore(test_redis)
    second_store = RedisTokenBucketStore(test_redis)
    bucket = _bucket('rate-limit:test:shared', burst=13)

    stores = (first_store, second_store) * 20
    results = await asyncio.gather(*(store.acquire((bucket,), timeout_ms=1000) for store in stores))

    assert sum(result.allowed for result in results) == 13


@pytest.mark.anyio
async def test_redis_atomic_rejection(test_redis: Redis) -> None:
    store = RedisTokenBucketStore(test_redis)
    exhausted = _bucket('rate-limit:test:exhausted')
    untouched = _bucket('rate-limit:test:untouched', burst=2)

    assert (await store.acquire((exhausted,), timeout_ms=1000)).allowed
    rejected = await store.acquire((exhausted, untouched), timeout_ms=1000)
    untouched_results = [await store.acquire((untouched,), timeout_ms=1000) for _ in range(3)]

    assert not rejected.allowed
    assert [result.allowed for result in untouched_results] == [True, True, False]


@pytest.mark.anyio
async def test_redis_scopes_isolated(test_redis: Redis) -> None:
    store = RedisTokenBucketStore(test_redis)
    first_scope = _bucket('rate-limit:test:scope-a')
    second_scope = _bucket('rate-limit:test:scope-b')

    first_results = [await store.acquire((first_scope,), timeout_ms=1000) for _ in range(2)]
    second_result = await store.acquire((second_scope,), timeout_ms=1000)

    assert [result.allowed for result in first_results] == [True, False]
    assert second_result.allowed


@pytest.mark.anyio
async def test_local_burst_concurrency() -> None:
    store = LocalTokenBucketStore(max_keys=10)
    bucket = _bucket('rate-limit:test:local-concurrent', burst=11)

    results = await asyncio.gather(*(store.acquire((bucket,)) for _ in range(80)))

    assert sum(result.allowed for result in results) == 11


@pytest.mark.anyio
async def test_local_atomic_rejection() -> None:
    store = LocalTokenBucketStore(max_keys=10)
    exhausted = _bucket('rate-limit:test:local-exhausted')
    untouched = _bucket('rate-limit:test:local-untouched', burst=2)

    assert (await store.acquire((exhausted,))).allowed
    rejected = await store.acquire((exhausted, untouched))
    untouched_results = [await store.acquire((untouched,)) for _ in range(3)]

    assert not rejected.allowed
    assert [result.allowed for result in untouched_results] == [True, True, False]


@pytest.mark.anyio
async def test_local_capacity_bound() -> None:
    store = LocalTokenBucketStore(max_keys=2)
    first_scope = _bucket('rate-limit:test:local-a', burst=2)
    second_scope = _bucket('rate-limit:test:local-b')
    overflow_scope = _bucket('rate-limit:test:local-c')

    assert (await store.acquire((first_scope,))).allowed
    assert (await store.acquire((second_scope,))).allowed
    overflow = await store.acquire((overflow_scope,))
    existing = await store.acquire((first_scope,))

    assert not overflow.allowed
    assert overflow.capacity_limited
    assert existing.allowed


@pytest.mark.anyio
async def test_empty_stage_allowed(test_redis: Redis) -> None:
    redis_store = RedisTokenBucketStore(test_redis)
    local_store = LocalTokenBucketStore(max_keys=1)

    redis_result, local_result = await asyncio.gather(
        redis_store.acquire((), timeout_ms=1),
        local_store.acquire(()),
    )

    assert redis_result.allowed
    assert local_result.allowed


@pytest.mark.anyio
async def test_duplicate_keys_rejected(test_redis: Redis) -> None:
    redis_store = RedisTokenBucketStore(test_redis)
    local_store = LocalTokenBucketStore(max_keys=1)
    bucket = _bucket('rate-limit:test:duplicate')

    with pytest.raises(ValueError, match='unique'):
        await redis_store.acquire((bucket, bucket), timeout_ms=1000)
    with pytest.raises(ValueError, match='unique'):
        await local_store.acquire((bucket, bucket))
