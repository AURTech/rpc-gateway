import asyncio
import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.infra.redis import build_key
from app.model.admission import AdmissionBackend, AdmissionMode, AdmissionRuntimePolicy
from app.services.admission.shadow import ShadowAdmission, ShadowAdmissionDispatcher
from app.services.admission.store import LocalTokenBucketStore, RedisTokenBucketStore, TokenBucketRequest, TokenBucketResult


class AdmissionRuntimePolicyProvider(Protocol):
    def get_runtime_policy(self) -> AdmissionRuntimePolicy: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class AdmissionDecision:
    limited: bool
    enforced: bool
    retry_after_ms: int = 0
    backend: str = 'redis'


class InflightAdmissionLimiter:
    def __init__(self) -> None:
        self._inflight = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, limit: int) -> AsyncGenerator[AdmissionDecision]:
        async with self._lock:
            limited = self._inflight >= limit
            entered = not limited
            if entered:
                self._inflight += 1
        decision = AdmissionDecision(
            limited=limited,
            enforced=limited,
            retry_after_ms=1000 if limited else 0,
            backend='local',
        )
        try:
            yield decision
        finally:
            if entered:
                async with self._lock:
                    self._inflight = max(0, self._inflight - 1)


class TokenBucketAdmissionEngine:
    def __init__(
        self,
        redis: Redis,
        policy_provider: AdmissionRuntimePolicyProvider,
        *,
        namespace: str,
        backend: AdmissionBackend = AdmissionBackend.REDIS,
        workers: int,
        expected_replicas: int,
        shadow_max_pending: int = 4096,
        shadow_workers: int = 16,
        shadow_redis_timeout_ms: int = 10,
        redis_store: RedisTokenBucketStore | None = None,
    ) -> None:
        if not namespace or ':' in namespace:
            raise ValueError('Admission namespace must be a non-empty segment.')
        if shadow_redis_timeout_ms < 1:
            raise ValueError('Shadow Redis timeout must be positive.')
        self._policy_provider = policy_provider
        self._namespace = namespace
        self._backend = backend
        self._hash_tag = f'{{admission-{namespace}}}'
        self._workers = max(1, workers)
        self._expected_replicas = max(1, expected_replicas)
        self._shadow_redis_timeout_ms = shadow_redis_timeout_ms
        self._redis_store = redis_store or RedisTokenBucketStore(redis)
        self._local_stores: dict[AdmissionMode, tuple[int, LocalTokenBucketStore]] = {}
        self._redis_inflight = {AdmissionMode.SHADOW: 0, AdmissionMode.ENFORCE: 0}
        self._redis_lock = asyncio.Lock()
        self._shadow = ShadowAdmissionDispatcher(
            namespace=namespace,
            max_pending=shadow_max_pending,
            workers=shadow_workers,
            writer=self._evaluate_shadow,
        )

    async def start(self) -> None:
        await self._shadow.start()

    async def close(self, *, drain_seconds: float) -> None:
        await self._shadow.close(drain_seconds=drain_seconds)

    def build_bucket(
        self,
        policy: AdmissionRuntimePolicy,
        *,
        scope: str,
        value: str,
        rps: int,
        burst: int,
    ) -> TokenBucketRequest:
        digest = hashlib.sha256(value.encode()).hexdigest()[:32]
        key = build_key('admission', 'v1', self._hash_tag, policy.mode.value, scope, digest)
        return TokenBucketRequest(key=key, rps=rps, burst=burst)

    async def admit(
        self,
        policy: AdmissionRuntimePolicy,
        buckets: tuple[TokenBucketRequest, ...],
    ) -> AdmissionDecision:
        self._clear_inactive_stores(policy.mode)
        if policy.mode is AdmissionMode.DISABLED:
            return AdmissionDecision(limited=False, enforced=False)
        if policy.mode is AdmissionMode.SHADOW:
            admission = ShadowAdmission(policy=policy, buckets=buckets)
            queued = self._shadow.submit(admission)
            backend = 'shadow' if queued else 'shadow_drop'
            return AdmissionDecision(limited=False, enforced=False, backend=backend)
        return await self._acquire(policy, buckets, redis_timeout_ms=policy.redis_timeout_ms)

    async def _evaluate_shadow(self, admission: ShadowAdmission) -> None:
        policy = self._policy_provider.get_runtime_policy()
        if policy.mode is not AdmissionMode.SHADOW or policy.version != admission.policy.version:
            return
        redis_timeout_ms = min(admission.policy.redis_timeout_ms, self._shadow_redis_timeout_ms)
        await self._acquire(admission.policy, admission.buckets, redis_timeout_ms=redis_timeout_ms)

    async def _acquire(
        self,
        policy: AdmissionRuntimePolicy,
        buckets: tuple[TokenBucketRequest, ...],
        *,
        redis_timeout_ms: int,
    ) -> AdmissionDecision:
        if self._backend is AdmissionBackend.LOCAL:
            # Local buckets live only in this API process, reset on restart, and are not
            # shared across workers or replicas. Use this backend only when one process
            # owns the complete admission budget.
            return await self._acquire_local(policy, buckets)

        entered = await self._enter_redis(policy.mode, policy.redis_admission_per_worker)
        result: TokenBucketResult | None = None
        if entered:
            # A failed or timed-out Redis acquire leaves result unset and degrades to the
            # local bucket below; the admission decision stays correct, only the shared
            # budget narrows to this process.
            try:
                with suppress(TimeoutError, RedisError, TypeError, ValueError):
                    result = await self._redis_store.acquire(buckets, timeout_ms=redis_timeout_ms)
            finally:
                await self._leave_redis(policy.mode)
        if result is not None:
            return self._make_decision(
                limited=not result.allowed,
                retry_after_ms=result.retry_after_ms,
                mode=policy.mode,
                backend='redis',
            )
        return await self._acquire_local(policy, buckets)

    async def _acquire_local(
        self,
        policy: AdmissionRuntimePolicy,
        buckets: tuple[TokenBucketRequest, ...],
    ) -> AdmissionDecision:
        local_store = self._get_local_store(policy.mode, policy.fallback_max_keys_per_worker)
        local_buckets = tuple(self._local_bucket(bucket) for bucket in buckets)
        result = await local_store.acquire(local_buckets)
        self._discard_obsolete_store(policy.mode, local_store)
        return self._make_decision(
            limited=not result.allowed,
            retry_after_ms=result.retry_after_ms,
            mode=policy.mode,
            backend='local',
        )

    def _local_bucket(self, bucket: TokenBucketRequest) -> TokenBucketRequest:
        process_count = self._workers * self._expected_replicas
        rps = bucket.rps / process_count
        burst = max(1, bucket.burst // process_count)
        return TokenBucketRequest(key=bucket.key, rps=rps, burst=burst, cost=bucket.cost)

    def _get_local_store(self, mode: AdmissionMode, max_keys: int) -> LocalTokenBucketStore:
        saved = self._local_stores.get(mode)
        if saved is None or saved[0] != max_keys:
            store = LocalTokenBucketStore(max_keys=max_keys)
            self._local_stores[mode] = (max_keys, store)
            return store
        return saved[1]

    def _clear_inactive_stores(self, mode: AdmissionMode) -> None:
        if mode is AdmissionMode.DISABLED:
            self._local_stores.clear()
            return
        inactive_modes = [saved_mode for saved_mode in self._local_stores if saved_mode is not mode]
        for inactive_mode in inactive_modes:
            self._local_stores.pop(inactive_mode, None)

    def _discard_obsolete_store(self, mode: AdmissionMode, store: LocalTokenBucketStore) -> None:
        if self._policy_provider.get_runtime_policy().mode is mode:
            return
        saved = self._local_stores.get(mode)
        if saved is not None and saved[1] is store:
            self._local_stores.pop(mode, None)

    def _make_decision(
        self,
        *,
        limited: bool,
        retry_after_ms: int,
        mode: AdmissionMode,
        backend: str,
    ) -> AdmissionDecision:
        enforced = limited and mode is AdmissionMode.ENFORCE
        return AdmissionDecision(
            limited=limited,
            enforced=enforced,
            retry_after_ms=retry_after_ms,
            backend=backend,
        )

    async def _enter_redis(self, mode: AdmissionMode, limit: int) -> bool:
        async with self._redis_lock:
            if self._redis_inflight[mode] >= limit:
                return False
            self._redis_inflight[mode] += 1
            return True

    async def _leave_redis(self, mode: AdmissionMode) -> None:
        async with self._redis_lock:
            self._redis_inflight[mode] = max(0, self._redis_inflight[mode] - 1)
