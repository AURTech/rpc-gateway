from collections import deque
from collections.abc import AsyncGenerator

import pytest
from app.infra import redis
from app.infra.redis import hold_redis_token_lease
from app.model.blockchain import Chain
from app.services.base import Manager
from app.services.system_jsonrpc_cache.limits import RETENTION_CLEANUP_LEASE_SECONDS
from app.services.system_jsonrpc_cache.retention import RetentionCleanupResult
from jobs.system_jsonrpc_cache import retention as retention_job
from redis.asyncio import Redis

pytestmark = pytest.mark.anyio


class _Log:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)


class _Manager:
    def __init__(self, results: list[RetentionCleanupResult | Exception]) -> None:
        self._results = deque(results)
        self.offsets: list[int] = []

    async def delete_expired(self, *, start_offset: int = 0) -> RetentionCleanupResult:
        self.offsets.append(start_offset)
        result = self._results.popleft()
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
async def manager_redis(test_redis: Redis) -> AsyncGenerator[Redis]:
    Manager.set_redis(test_redis)
    try:
        yield test_redis
    finally:
        Manager.clear_redis()


def _result(*, timed_out_chains: tuple[Chain, ...] = ()) -> RetentionCleanupResult:
    return RetentionCleanupResult(
        deleted_rows=2,
        deleted_bytes=10,
        attempted_batches=3,
        completed_batches=3 - len(timed_out_chains),
        timed_out_chains=timed_out_chains,
        elapsed_ms=20,
    )


def _set_manager(monkeypatch: pytest.MonkeyPatch, manager: _Manager) -> None:
    def make_manager(_store: object, _retention_seconds: object, *, max_batch_bytes: int) -> _Manager:
        assert max_batch_bytes == 32 * 1024 * 1024
        return manager

    monkeypatch.setattr(retention_job, 'RetentionManager', make_manager)


async def test_job_rotates_start_offset(
    manager_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del manager_redis
    manager = _Manager([_result(), _result()])
    _set_manager(monkeypatch, manager)

    first = await retention_job.delete_expired_retained_entries()
    second = await retention_job.delete_expired_retained_entries()

    assert first['status'] == 'ok'
    assert second['status'] == 'ok'
    assert manager.offsets == [0, 1]


async def test_job_reports_partial_cleanup(
    manager_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del manager_redis
    manager = _Manager([_result(timed_out_chains=(Chain.SOLANA,))])
    log = _Log()
    _set_manager(monkeypatch, manager)
    monkeypatch.setattr(retention_job, 'log', log)

    result = await retention_job.delete_expired_retained_entries()

    assert result['status'] == 'partial'
    assert result['timed_out_chains'] == ['solana']
    assert result['attempted_batches'] == 3
    assert result['completed_batches'] == 2
    assert len(log.warning_messages) == 1
    assert 'TimedOutChains:solana' in log.warning_messages[0]


async def test_job_reports_busy_without_advancing_cursor(manager_redis: Redis) -> None:
    lease_key = redis.build_key('system_jsonrpc_cache', 'v1', 'retention_cleanup')
    cursor_key = redis.build_key('system_jsonrpc_cache', 'v1', 'retention_cleanup_cursor')
    async with hold_redis_token_lease(manager_redis, lease_key, ttl_seconds=RETENTION_CLEANUP_LEASE_SECONDS) as lease:
        assert lease is not None
        result = await retention_job.delete_expired_retained_entries()

    assert result['status'] == 'busy'
    assert await manager_redis.get(cursor_key) is None


async def test_job_reports_unexpected_failure(
    manager_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del manager_redis
    manager = _Manager([RuntimeError('database unavailable')])
    log = _Log()
    _set_manager(monkeypatch, manager)
    monkeypatch.setattr(retention_job, 'log', log)

    result = await retention_job.delete_expired_retained_entries()

    assert result['status'] == 'failed'
    assert result['attempted_batches'] == 0
    assert len(log.warning_messages) == 1
    assert 'database unavailable' in log.warning_messages[0]
