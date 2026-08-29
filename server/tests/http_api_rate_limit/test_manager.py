import asyncio
from datetime import UTC, datetime

import pytest
from app.model.admission import AdmissionMode
from app.model.http_api_rate_limit import HttpApiRateLimitBucket, HttpApiRateLimitPolicyItem
from app.services.admission import AdmissionDecision
from app.services.http_api_rate_limit import HttpApiAdmissionManager
from redis.asyncio import Redis


class _PolicyProvider:
    def __init__(self, policy: HttpApiRateLimitPolicyItem) -> None:
        self.policy = policy

    def get_policy(self) -> HttpApiRateLimitPolicyItem:
        return self.policy


def _policy(mode: AdmissionMode, *, max_inflight: int = 5) -> HttpApiRateLimitPolicyItem:
    timestamp = datetime.now(UTC)
    bucket = HttpApiRateLimitBucket(rps=1, burst=8)
    return HttpApiRateLimitPolicyItem(
        mode=mode,
        max_inflight_per_worker=max_inflight,
        redis_timeout_ms=10,
        redis_admission_per_worker=100,
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
@pytest.mark.parametrize('mode', list(AdmissionMode))
async def test_inflight_limit_is_always_enforced(test_redis: Redis, mode: AdmissionMode) -> None:
    manager = HttpApiAdmissionManager(
        test_redis,
        _PolicyProvider(_policy(mode)),
        workers=1,
        expected_replicas=1,
    )
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
    assert sum(decision.enforced for decision in decisions) == 15

    async with manager.acquire_inflight() as decision:
        assert not decision.limited
        assert not decision.enforced
