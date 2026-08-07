import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.model.admission import AdmissionBackend, AdmissionMode
from app.model.jsonrpc_rate_limit import JsonRpcRateLimitBucket, JsonRpcRateLimitPolicyItem
from app.services.admission import AdmissionDecision
from app.services.admission.store import RedisTokenBucketStore, TokenBucketRequest, TokenBucketResult
from app.services.jsonrpc_rate_limit import JsonRpcAdmissionManager
from redis.asyncio import Redis
from redis.exceptions import RedisError


class _PolicyProvider:
    def __init__(self, policy: JsonRpcRateLimitPolicyItem) -> None:
        self.policy = policy

    def get_policy(self) -> JsonRpcRateLimitPolicyItem:
        return self.policy


class _FailingStore(RedisTokenBucketStore):
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    async def acquire(self, buckets: tuple[TokenBucketRequest, ...], *, timeout_ms: int) -> TokenBucketResult:
        raise self._failure


class _BlockingStore(RedisTokenBucketStore):
    def __init__(self, result: TokenBucketResult) -> None:
        self._result = result
        self._started = 0
        self._condition = asyncio.Condition()
        self._release = asyncio.Event()

    async def acquire(self, buckets: tuple[TokenBucketRequest, ...], *, timeout_ms: int) -> TokenBucketResult:
        async with self._condition:
            self._started += 1
            self._condition.notify_all()
        await self._release.wait()
        return self._result

    async def wait_started(self, count: int) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self._started >= count)

    def release(self) -> None:
        self._release.set()


class _RecordingStore(RedisTokenBucketStore):
    def __init__(self) -> None:
        self.calls: list[tuple[TokenBucketRequest, ...]] = []
        self._condition = asyncio.Condition()

    async def acquire(self, buckets: tuple[TokenBucketRequest, ...], *, timeout_ms: int) -> TokenBucketResult:
        async with self._condition:
            self.calls.append(buckets)
            self._condition.notify_all()
        return TokenBucketResult(allowed=True)

    async def wait_calls(self, count: int) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: len(self.calls) >= count)


class _SequenceStore(RedisTokenBucketStore):
    def __init__(self) -> None:
        self.calls = 0
        self._condition = asyncio.Condition()

    async def acquire(self, buckets: tuple[TokenBucketRequest, ...], *, timeout_ms: int) -> TokenBucketResult:
        async with self._condition:
            self.calls += 1
            self._condition.notify_all()
        if self.calls == 1:
            raise RuntimeError('Unexpected store failure.')
        return TokenBucketResult(allowed=True)

    async def wait_calls(self, count: int) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self.calls >= count)


def _policy(
    *,
    mode: AdmissionMode = AdmissionMode.ENFORCE,
    burst: int = 8,
    max_inflight: int = 5,
    redis_admission: int = 100,
) -> JsonRpcRateLimitPolicyItem:
    timestamp = datetime.now(UTC)
    bucket = JsonRpcRateLimitBucket(rps=1, burst=burst)
    return JsonRpcRateLimitPolicyItem(
        mode=mode,
        max_inflight_per_worker=max_inflight,
        redis_timeout_ms=10,
        redis_admission_per_worker=redis_admission,
        fallback_max_keys_per_worker=1000,
        global_limit=bucket,
        ip_limit=bucket,
        account_limit=bucket,
        app_limit=bucket,
        version=1,
        modified_by_account_id=None,
        created_at=timestamp,
        modified_at=timestamp,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    'failure',
    [TimeoutError(), RedisError('Redis unavailable.')],
    ids=['timeout', 'redis-error'],
)
async def test_failure_uses_fallback(test_redis: Redis, failure: Exception) -> None:
    provider = _PolicyProvider(_policy())
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=2,
        expected_replicas=2,
        redis_store=_FailingStore(failure),
    )

    decisions = [await manager.acquire_pre_auth('192.0.2.1') for _ in range(3)]

    assert [decision.backend for decision in decisions] == ['local', 'local', 'local']
    assert [decision.limited for decision in decisions] == [False, False, True]
    assert decisions[-1].enforced
    assert decisions[-1].retry_after_ms > 0


@pytest.mark.anyio
async def test_local_backend_bypasses_redis(test_redis: Redis) -> None:
    provider = _PolicyProvider(_policy(burst=2))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        backend=AdmissionBackend.LOCAL,
        workers=1,
        expected_replicas=1,
        redis_store=_FailingStore(AssertionError('Redis store must not be called.')),
    )

    decisions = [await manager.acquire_pre_auth('192.0.2.1') for _ in range(3)]

    assert [decision.backend for decision in decisions] == ['local', 'local', 'local']
    assert [decision.limited for decision in decisions] == [False, False, True]
    assert decisions[-1].enforced


@pytest.mark.anyio
async def test_local_backend_preserves_shadow_semantics(test_redis: Redis) -> None:
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW, burst=1))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        backend=AdmissionBackend.LOCAL,
        workers=1,
        expected_replicas=1,
        shadow_workers=1,
        redis_store=_FailingStore(AssertionError('Redis store must not be called.')),
    )
    await manager.start()

    decisions = [await manager.acquire_pre_auth('192.0.2.2') for _ in range(2)]
    await asyncio.wait_for(_wait_shadow_idle(manager), timeout=1)
    await manager.close(drain_seconds=1)

    assert [decision.backend for decision in decisions] == ['shadow', 'shadow']
    assert all(not decision.limited and not decision.enforced for decision in decisions)


@pytest.mark.anyio
async def test_redis_admission_fallback(test_redis: Redis) -> None:
    store = _BlockingStore(TokenBucketResult(allowed=True))
    provider = _PolicyProvider(_policy(redis_admission=1))
    manager = JsonRpcAdmissionManager(test_redis, provider, workers=1, expected_replicas=1, redis_store=store)

    redis_task = asyncio.create_task(manager.acquire_pre_auth('192.0.2.2'))
    await asyncio.wait_for(store.wait_started(1), timeout=1)
    fallback_decision = await manager.acquire_pre_auth('192.0.2.3')
    store.release()
    redis_decision = await redis_task

    assert fallback_decision.backend == 'local'
    assert not fallback_decision.limited
    assert redis_decision.backend == 'redis'
    assert not redis_decision.limited


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('mode', 'enforced_count'),
    [
        (AdmissionMode.DISABLED, 15),
        (AdmissionMode.SHADOW, 15),
        (AdmissionMode.ENFORCE, 15),
    ],
)
async def test_inflight_concurrency(test_redis: Redis, mode: AdmissionMode, enforced_count: int) -> None:
    provider = _PolicyProvider(_policy(mode=mode, max_inflight=5))
    manager = JsonRpcAdmissionManager(test_redis, provider, workers=1, expected_replicas=1)
    release = asyncio.Event()
    condition = asyncio.Condition()
    entered = 0

    async def acquire() -> AdmissionDecision:
        nonlocal entered
        async with manager.acquire_inflight() as decision:
            async with condition:
                entered += 1
                condition.notify_all()
            await release.wait()
            return decision

    tasks = [asyncio.create_task(acquire()) for _ in range(20)]
    async with condition:
        await asyncio.wait_for(condition.wait_for(lambda: entered == 20), timeout=1)
    release.set()
    decisions = await asyncio.gather(*tasks)

    assert sum(decision.limited for decision in decisions) == 15
    assert sum(decision.enforced for decision in decisions) == enforced_count


@pytest.mark.anyio
async def test_shadow_does_not_wait_for_redis(test_redis: Redis) -> None:
    store = _BlockingStore(TokenBucketResult(allowed=False, retry_after_ms=125))
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW, redis_admission=100))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_workers=4,
        redis_store=store,
    )
    await manager.start()

    shadow_decisions = await asyncio.wait_for(
        asyncio.gather(*(manager.acquire_pre_auth(f'192.0.2.{index}') for index in range(20))),
        timeout=0.1,
    )
    await asyncio.wait_for(store.wait_started(4), timeout=1)
    provider.policy = provider.policy.model_copy(update={'mode': AdmissionMode.ENFORCE, 'version': 2})
    enforce_tasks = [asyncio.create_task(manager.acquire_pre_auth(f'198.51.100.{index}')) for index in range(20)]
    await asyncio.wait_for(store.wait_started(24), timeout=1)
    store.release()
    enforce_decisions = await asyncio.gather(*enforce_tasks)
    await manager.close(drain_seconds=1)

    assert all(not decision.limited and not decision.enforced for decision in shadow_decisions)
    assert all(decision.backend == 'shadow' for decision in shadow_decisions)
    assert all(decision.limited and decision.enforced for decision in enforce_decisions)
    assert all(decision.retry_after_ms == 125 for decision in enforce_decisions)


@pytest.mark.anyio
async def test_shadow_queue_is_bounded(test_redis: Redis) -> None:
    store = _BlockingStore(TokenBucketResult(allowed=True))
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_max_pending=1,
        shadow_workers=1,
        redis_store=store,
    )
    await manager.start()

    first = await manager.acquire_pre_auth('192.0.2.1')
    await asyncio.wait_for(store.wait_started(1), timeout=1)
    second = await manager.acquire_pre_auth('192.0.2.2')
    overflow = await manager.acquire_pre_auth('192.0.2.3')
    store.release()
    await manager.close(drain_seconds=1)

    assert first.backend == 'shadow'
    assert second.backend == 'shadow'
    assert overflow.backend == 'shadow_drop'
    assert not overflow.limited and not overflow.enforced


@pytest.mark.anyio
async def test_modes_use_separate_redis_keys(test_redis: Redis) -> None:
    store = _RecordingStore()
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_workers=1,
        redis_store=store,
    )
    await manager.start()

    await manager.acquire_pre_auth('192.0.2.10')
    await asyncio.wait_for(store.wait_calls(1), timeout=1)
    provider.policy = provider.policy.model_copy(update={'mode': AdmissionMode.ENFORCE, 'version': 2})
    await manager.acquire_pre_auth('192.0.2.10')
    await manager.close(drain_seconds=1)

    shadow_call, enforce_call = store.calls
    assert all(':shadow:' in bucket.key for bucket in shadow_call)
    assert all(':enforce:' in bucket.key for bucket in enforce_call)
    assert {bucket.key for bucket in shadow_call}.isdisjoint(bucket.key for bucket in enforce_call)


@pytest.mark.anyio
async def test_shadow_does_not_take_enforce_admission(test_redis: Redis) -> None:
    store = _BlockingStore(TokenBucketResult(allowed=True))
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW, redis_admission=1))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_workers=1,
        redis_store=store,
    )
    await manager.start()

    await manager.acquire_pre_auth('192.0.2.20')
    await asyncio.wait_for(store.wait_started(1), timeout=1)
    provider.policy = provider.policy.model_copy(update={'mode': AdmissionMode.ENFORCE, 'version': 2})
    enforce_task = asyncio.create_task(manager.acquire_pre_auth('192.0.2.21'))
    await asyncio.wait_for(store.wait_started(2), timeout=1)
    store.release()
    decision = await enforce_task
    await manager.close(drain_seconds=1)

    assert decision.backend == 'redis'
    assert not decision.limited


@pytest.mark.anyio
async def test_stale_shadow_policy_dropped(test_redis: Redis) -> None:
    store = _BlockingStore(TokenBucketResult(allowed=True))
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_workers=1,
        redis_store=store,
    )
    await manager.start()

    await manager.acquire_pre_auth('192.0.2.40')
    await asyncio.wait_for(store.wait_started(1), timeout=1)
    for index in range(3):
        await manager.acquire_pre_auth(f'192.0.2.{41 + index}')
    provider.policy = provider.policy.model_copy(update={'version': 2})
    store.release()
    await manager.acquire_pre_auth('192.0.2.44')
    await asyncio.wait_for(store.wait_started(2), timeout=1)
    await manager.close(drain_seconds=1)

    assert store._started == 2


@pytest.mark.anyio
async def test_fallback_stores_are_isolated(test_redis: Redis) -> None:
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW, burst=2000, redis_admission=100))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_max_pending=2000,
        shadow_workers=16,
        redis_store=_FailingStore(RedisError('Redis unavailable.')),
    )
    await manager.start()

    await asyncio.gather(*(manager.acquire_pre_auth(f'2001:db8::{index:x}') for index in range(999)))
    await asyncio.wait_for(_wait_shadow_idle(manager), timeout=1)
    provider.policy = provider.policy.model_copy(update={'mode': AdmissionMode.ENFORCE, 'version': 2})
    decision = await manager.acquire_pre_auth('198.51.100.1')
    await manager.close(drain_seconds=1)

    assert decision.backend == 'local'
    assert not decision.limited


async def _wait_shadow_idle(manager: JsonRpcAdmissionManager) -> None:
    while manager._engine._shadow.pending > 0:
        await asyncio.sleep(0)


@pytest.mark.anyio
async def test_shadow_close_cancels_blocked_writer(test_redis: Redis) -> None:
    store = _BlockingStore(TokenBucketResult(allowed=True))
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_workers=1,
        redis_store=store,
    )
    await manager.start()

    await manager.acquire_pre_auth('192.0.2.30')
    await asyncio.wait_for(store.wait_started(1), timeout=1)
    await asyncio.wait_for(manager.close(drain_seconds=0), timeout=1)

    shadow_tasks = [task for task in asyncio.all_tasks() if task.get_name().startswith('admission-public-jsonrpc-shadow-')]
    assert not shadow_tasks


@pytest.mark.anyio
async def test_shadow_worker_survives_error(test_redis: Redis) -> None:
    store = _SequenceStore()
    provider = _PolicyProvider(_policy(mode=AdmissionMode.SHADOW))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        shadow_workers=1,
        redis_store=store,
    )
    await manager.start()

    await manager.acquire_pre_auth('192.0.2.50')
    await manager.acquire_pre_auth('192.0.2.51')
    await asyncio.wait_for(store.wait_calls(2), timeout=1)
    await manager.close(drain_seconds=1)

    assert store.calls == 2


@pytest.mark.anyio
async def test_disabled_bypasses_store(test_redis: Redis) -> None:
    provider = _PolicyProvider(_policy(mode=AdmissionMode.DISABLED, max_inflight=1))
    manager = JsonRpcAdmissionManager(
        test_redis,
        provider,
        workers=1,
        expected_replicas=1,
        redis_store=_FailingStore(AssertionError('Store must not be called.')),
    )

    decisions = await asyncio.gather(*(manager.acquire_pre_auth(f'192.0.2.{index}') for index in range(10)))

    assert all(not decision.limited and not decision.enforced for decision in decisions)


@pytest.mark.anyio
async def test_stage_scopes_are_isolated(test_redis: Redis) -> None:
    store = _RecordingStore()
    provider = _PolicyProvider(_policy())
    manager = JsonRpcAdmissionManager(test_redis, provider, workers=1, expected_replicas=1, redis_store=store)

    await manager.acquire_pre_auth('192.0.2.10')
    await manager.acquire_pre_auth('192.0.2.11')
    await manager.acquire_post_auth('account-a', 'app-a')
    await manager.acquire_post_auth('account-a', 'app-b')

    pre_auth_a, pre_auth_b, post_auth_a, post_auth_b = store.calls
    assert pre_auth_a[0].key == pre_auth_b[0].key
    assert pre_auth_a[1].key != pre_auth_b[1].key
    assert post_auth_a[0].key == post_auth_b[0].key
    assert post_auth_a[1].key != post_auth_b[1].key
    raw_scopes = ('192.0.2.10', '192.0.2.11', 'account-a', 'app-a', 'app-b')
    assert all(raw not in bucket.key for call in store.calls for bucket in call for raw in raw_scopes)


def test_import_excludes_orm(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment['ENV_FILE'] = str(tmp_path / 'missing.env')
    environment['APP_API_KEY_MASTER_KEY'] = 'test-app-api-key-master-secret-32-bytes'
    script = (
        'import sys\n'
        'import app.services.jsonrpc_rate_limit\n'
        "loaded = [name for name in sys.modules if name == 'app.orm' or name.startswith('app.orm.')]\n"
        'assert not loaded, loaded\n'
    )

    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
