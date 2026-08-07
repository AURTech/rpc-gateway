import pytest
from app.core.config import CONF
from redis.asyncio import Redis

from scripts import taskiq_stream_cleanup


async def _add_messages(redis: Redis, stream: str, count: int) -> list[str]:
    return [str(await redis.xadd(stream, {'data': str(index)})) for index in range(count)]


@pytest.mark.anyio
async def test_cleanup_preserves_pending_and_undelivered_messages(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup'
    group = taskiq_stream_cleanup.DEFAULT_CONSUMER_GROUP
    await test_redis.xgroup_create(stream, group, id='0-0', mkstream=True)
    message_ids = await _add_messages(test_redis, stream, 5)
    delivered = await test_redis.xreadgroup(group, 'worker-1', {stream: '>'}, count=4)
    assert [message_id for message_id, _payload in delivered[0][1]] == message_ids[:4]
    await test_redis.xack(stream, group, message_ids[0], message_ids[1], message_ids[3])

    before, after, removed = await taskiq_stream_cleanup.trim_stream(
        test_redis,
        stream=stream,
        expected_groups=(group,),
        batch_size=2,
        exact=True,
    )

    assert before.boundary == message_ids[2]
    assert removed == 2
    assert [message_id for message_id, _payload in await test_redis.xrange(stream)] == message_ids[2:]
    assert after.groups[0].pending == 1
    assert after.groups[0].oldest_pending_id == message_ids[2]
    assert after.groups[0].last_delivered_id == message_ids[3]
    assert after.groups[0].lag == 1


@pytest.mark.anyio
async def test_cleanup_without_pending_keeps_last_delivered_message(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-no-pending'
    group = taskiq_stream_cleanup.DEFAULT_CONSUMER_GROUP
    await test_redis.xgroup_create(stream, group, id='0-0', mkstream=True)
    message_ids = await _add_messages(test_redis, stream, 4)
    delivered = await test_redis.xreadgroup(group, 'worker-1', {stream: '>'}, count=3)
    delivered_ids = [message_id for message_id, _payload in delivered[0][1]]
    await test_redis.xack(stream, group, *delivered_ids)

    before, after, removed = await taskiq_stream_cleanup.trim_stream(
        test_redis,
        stream=stream,
        expected_groups=(group,),
        batch_size=2,
        exact=True,
    )

    assert before.boundary == message_ids[2]
    assert removed == 2
    assert [message_id for message_id, _payload in await test_redis.xrange(stream)] == message_ids[2:]
    assert after.groups[0].pending == 0
    assert after.groups[0].last_delivered_id == message_ids[2]
    assert after.groups[0].lag == 1


@pytest.mark.anyio
async def test_cleanup_rejects_unexpected_consumer_group(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-groups'
    await test_redis.xgroup_create(stream, 'taskiq', id='0-0', mkstream=True)
    await test_redis.xgroup_create(stream, 'other', id='0-0')
    await _add_messages(test_redis, stream, 1)

    with pytest.raises(taskiq_stream_cleanup.StreamCleanupError, match='Consumer groups changed'):
        await taskiq_stream_cleanup.load_stream_state(test_redis, stream, ('taskiq',))


@pytest.mark.anyio
async def test_cleanup_uses_oldest_boundary_across_groups(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-multiple-groups'
    message_ids = await _add_messages(test_redis, stream, 6)
    await test_redis.xgroup_create(stream, 'taskiq', id='0-0')
    await test_redis.xgroup_create(stream, 'other', id='0-0')
    taskiq_delivered = await test_redis.xreadgroup('taskiq', 'worker-1', {stream: '>'}, count=5)
    other_delivered = await test_redis.xreadgroup('other', 'worker-2', {stream: '>'}, count=4)
    await test_redis.xack(stream, 'taskiq', *[message_id for message_id, _payload in taskiq_delivered[0][1]])
    await test_redis.xack(
        stream,
        'other',
        *[message_id for message_id, _payload in other_delivered[0][1]][:2],
    )

    before, after, removed = await taskiq_stream_cleanup.trim_stream(
        test_redis,
        stream=stream,
        expected_groups=('taskiq', 'other'),
        batch_size=2,
        exact=True,
    )

    assert before.boundary == message_ids[2]
    assert removed == 2
    assert [message_id for message_id, _payload in await test_redis.xrange(stream)] == message_ids[2:]
    assert {group.name: group.pending for group in after.groups} == {'other': 2, 'taskiq': 0}


@pytest.mark.anyio
async def test_atomic_trim_rejects_changed_group_without_deleting(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-race'
    group = taskiq_stream_cleanup.DEFAULT_CONSUMER_GROUP
    message_ids = await _add_messages(test_redis, stream, 4)
    await test_redis.xgroup_create(stream, group, id='0-0')
    delivered = await test_redis.xreadgroup(group, 'worker-1', {stream: '>'}, count=3)
    await test_redis.xack(stream, group, *[message_id for message_id, _payload in delivered[0][1]])
    state = await taskiq_stream_cleanup.load_stream_state(test_redis, stream, (group,))
    await test_redis.xgroup_create(stream, 'late-group', id='0-0')

    with pytest.raises(taskiq_stream_cleanup.StreamCleanupError, match='state changed before trim'):
        await taskiq_stream_cleanup._trim_batch(test_redis, state, approximate=False, batch_size=2)

    assert [message_id for message_id, _payload in await test_redis.xrange(stream)] == message_ids


@pytest.mark.anyio
async def test_cleanup_approximate_mode_does_not_fall_through_to_exact(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-approximate-only'
    group = taskiq_stream_cleanup.DEFAULT_CONSUMER_GROUP
    await test_redis.xgroup_create(stream, group, id='0-0', mkstream=True)
    message_ids = await _add_messages(test_redis, stream, 4)
    delivered = await test_redis.xreadgroup(group, 'worker-1', {stream: '>'}, count=3)
    await test_redis.xack(stream, group, *[message_id for message_id, _payload in delivered[0][1]])

    _before, _after, removed = await taskiq_stream_cleanup.trim_stream(
        test_redis,
        stream=stream,
        expected_groups=(group,),
        batch_size=2,
        exact=False,
    )

    assert removed == 0
    assert [message_id for message_id, _payload in await test_redis.xrange(stream)] == message_ids


@pytest.mark.anyio
async def test_cleanup_repeats_approximate_batches(monkeypatch: pytest.MonkeyPatch, test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-batches'
    group = taskiq_stream_cleanup.DEFAULT_CONSUMER_GROUP
    await test_redis.xgroup_create(stream, group, id='0-0', mkstream=True)
    await _add_messages(test_redis, stream, 1)
    delivered = await test_redis.xreadgroup(group, 'worker-1', {stream: '>'}, count=1)
    await test_redis.xack(stream, group, delivered[0][1][0][0])
    batch_results = iter([2, 1, 0])
    calls: list[bool] = []

    async def fake_trim_batch(
        _redis: Redis,
        _state: taskiq_stream_cleanup.StreamState,
        *,
        approximate: bool,
        batch_size: int,
    ) -> int:
        assert batch_size == 2
        calls.append(approximate)
        return next(batch_results)

    monkeypatch.setattr(taskiq_stream_cleanup, '_trim_batch', fake_trim_batch)

    _before, _after, removed = await taskiq_stream_cleanup.trim_stream(
        test_redis,
        stream=stream,
        expected_groups=(group,),
        batch_size=2,
        exact=False,
    )

    assert removed == 3
    assert calls == [True, True, True]


@pytest.mark.anyio
async def test_cleanup_dry_run_does_not_trim(test_redis: Redis) -> None:
    stream = f'{CONF.PROJECT_NAME}:taskiq-stream-cleanup-dry-run'
    group = taskiq_stream_cleanup.DEFAULT_CONSUMER_GROUP
    await test_redis.xgroup_create(stream, group, id='0-0', mkstream=True)
    message_ids = await _add_messages(test_redis, stream, 3)
    delivered = await test_redis.xreadgroup(group, 'worker-1', {stream: '>'}, count=2)
    await test_redis.xack(stream, group, *[message_id for message_id, _payload in delivered[0][1]])

    result = await taskiq_stream_cleanup.run_cleanup(
        redis_url=CONF.TEST_REDIS_URL,
        stream=stream,
        expected_groups=(group,),
        batch_size=2,
        apply=False,
        exact=False,
    )

    assert result['mode'] == 'dry-run'
    assert [message_id for message_id, _payload in await test_redis.xrange(stream)] == message_ids
