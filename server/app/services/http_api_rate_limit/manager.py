from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol

from redis.asyncio import Redis

from app.model.admission import AdmissionBackend, AdmissionRuntimePolicy
from app.model.http_api_rate_limit import HttpApiRateLimitBucket, HttpApiRateLimitPolicyItem
from app.services.admission import (
    AdmissionDecision,
    InflightAdmissionLimiter,
    RedisTokenBucketStore,
    TokenBucketAdmissionEngine,
    TokenBucketRequest,
)


class HttpApiRateLimitPolicyProvider(Protocol):
    def get_policy(self) -> HttpApiRateLimitPolicyItem: ...


class HttpApiAdmissionManager:
    def __init__(
        self,
        redis: Redis,
        policy_provider: HttpApiRateLimitPolicyProvider,
        *,
        backend: AdmissionBackend = AdmissionBackend.REDIS,
        workers: int,
        expected_replicas: int,
        shadow_max_pending: int = 4096,
        shadow_workers: int = 16,
        shadow_redis_timeout_ms: int = 10,
        redis_store: RedisTokenBucketStore | None = None,
    ) -> None:
        self._policy_provider = policy_provider
        self._inflight = InflightAdmissionLimiter()
        self._engine = TokenBucketAdmissionEngine(
            redis,
            self,
            namespace='public-http-api',
            backend=backend,
            workers=workers,
            expected_replicas=expected_replicas,
            shadow_max_pending=shadow_max_pending,
            shadow_workers=shadow_workers,
            shadow_redis_timeout_ms=shadow_redis_timeout_ms,
            redis_store=redis_store,
        )

    def get_runtime_policy(self) -> AdmissionRuntimePolicy:
        return self._policy_provider.get_policy().to_runtime_policy()

    async def start(self) -> None:
        await self._engine.start()

    async def close(self, *, drain_seconds: float) -> None:
        await self._engine.close(drain_seconds=drain_seconds)

    @asynccontextmanager
    async def acquire_inflight(self) -> AsyncGenerator[AdmissionDecision]:
        policy = self._policy_provider.get_policy()
        async with self._inflight.acquire(policy.max_inflight_per_worker, policy.mode) as decision:
            yield decision

    async def acquire_pre_auth(self, client_ip: str) -> AdmissionDecision:
        policy = self._policy_provider.get_policy()
        runtime = policy.to_runtime_policy()
        buckets = (
            self._bucket(runtime, 'global', 'all', policy.global_limit),
            self._bucket(runtime, 'ip', client_ip or 'unknown', policy.ip_limit),
        )
        return await self._engine.admit(runtime, buckets)

    async def acquire_post_auth(self, account_id: str, app_id: str) -> AdmissionDecision:
        policy = self._policy_provider.get_policy()
        runtime = policy.to_runtime_policy()
        buckets = (
            self._bucket(runtime, 'account', account_id, policy.account_limit),
            self._bucket(runtime, 'app', app_id, policy.app_limit),
        )
        return await self._engine.admit(runtime, buckets)

    def _bucket(
        self,
        policy: AdmissionRuntimePolicy,
        scope: str,
        value: str,
        limit: HttpApiRateLimitBucket,
    ) -> TokenBucketRequest:
        return self._engine.build_bucket(policy, scope=scope, value=value, rps=limit.rps, burst=limit.burst)
