import pytest
from app.core.config import CONF
from app.infra import redis
from app.util import redis_key
from redis.asyncio import Redis


def test_build_key_uses_project_namespace() -> None:
    assert redis.build_key('rpc', 'usage', 'stream') == f'{CONF.PROJECT_NAME}:rpc:usage:stream'


def test_build_pattern_uses_project_namespace() -> None:
    assert redis.build_pattern('rpc', 'usage', '*') == f'{CONF.PROJECT_NAME}:rpc:usage:*'


def test_build_prefix_uses_project_namespace() -> None:
    assert redis.build_prefix('rpc', 'usage') == f'{CONF.PROJECT_NAME}:rpc:usage:'


@pytest.mark.anyio
async def test_delete_keys_matching_deletes_only_matched_keys(test_redis: Redis) -> None:
    keep_key = redis.build_key('rpc', 'routing', 'keep')
    delete_key = redis.build_key('rpc', 'routing', 'delete')
    await test_redis.set(keep_key, '1')
    await test_redis.set(delete_key, '1')

    deleted = await redis.delete_keys_matching(test_redis, redis.build_pattern('rpc', 'routing', 'delete'))

    assert deleted == 1
    assert await test_redis.get(delete_key) is None
    assert await test_redis.get(keep_key) == '1'


def test_join_key_rejects_pattern_chars() -> None:
    with pytest.raises(ValueError, match='Invalid Redis key part.'):
        redis_key.join_key('rpc-gateway', 'rpc', '*')


def test_validate_key_part_rejects_key_separator_and_pattern_chars() -> None:
    assert redis_key.validate_key_part('rpc-usage') == 'rpc-usage'
    for key_part in ['rpc:usage', '*', '?', '[', ']']:
        with pytest.raises(ValueError, match='Invalid Redis key part.'):
            redis_key.validate_key_part(key_part)


def test_join_pattern_allows_glob_part() -> None:
    assert redis_key.join_pattern('rpc-gateway', 'rpc', '*') == 'rpc-gateway:rpc:*'


def test_join_key_rejects_colon_part() -> None:
    with pytest.raises(ValueError, match='Invalid Redis key part.'):
        redis_key.join_key('rpc-gateway', 'rpc:usage')
