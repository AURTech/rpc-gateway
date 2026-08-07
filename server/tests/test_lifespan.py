from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from app import init_app
from app.core import lifespan as lifespan_module
from app.orm.account.account import Account
from app.services.base import Manager
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from tests.infra import truncate_test_tables


@pytest.mark.anyio
async def test_test_lifespan_uses_postgres_and_redis(app: FastAPI) -> None:
    user = await Account.create(email='lifespan@example.com')

    assert user.id
    assert Manager().redis is app.state.redis
    assert await app.state.redis.ping()


@pytest.mark.anyio
async def test_test_table_cleanup_removes_rows(app: FastAPI) -> None:
    await Account.create(email='cleanup@example.com')
    assert await Account.all().count() == 1
    await truncate_test_tables(app.state.test_schema)
    assert await Account.all().count() == 0


def test_manager_redis_access_requires_client() -> None:
    Manager.clear_redis()
    with pytest.raises(RuntimeError, match='Redis client has not been set.'):
        _ = Manager().redis


@pytest.mark.anyio
async def test_production_lifespan_requires_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_create_redis_client() -> None:
        raise SystemError('Redis init error')

    monkeypatch.setattr('app.core.lifespan.runtime.create_redis_client', fail_create_redis_client)
    application = init_app()
    with pytest.raises(SystemError, match='Redis init error'):
        async with LifespanManager(application):
            pass


@pytest.mark.anyio
async def test_lifespan_starts_only_v2_managers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeHealthDispatcher:
        async def start(self) -> None:
            calls.append('health-start')

        async def close(self, *, drain_seconds: float) -> None:
            calls.append('health-close')

    class FakeTipDispatcher:
        async def start(self) -> None:
            calls.append('tip-start')

        async def close(self, *, drain_seconds: float) -> None:
            calls.append('tip-close')

    class FakeCircuitManager:
        async def start(self) -> None:
            calls.append('circuit-start')

        async def close(self, *, drain_seconds: float) -> None:
            calls.append('circuit-close')

    class FakeUsageRecorder:
        async def start(self) -> None:
            calls.append('usage-start')

        async def close(self, *, drain_seconds: float) -> None:
            calls.append('usage-close')

    class FakeJsonRpcRateLimitPolicyManager:
        async def start(self) -> None:
            calls.append('rate-policy-start')

        async def close(self) -> None:
            calls.append('rate-policy-close')

    class FakeJsonRpcAdmissionManager:
        async def start(self) -> None:
            calls.append('rpc-admission-start')

        async def close(self, *, drain_seconds: float) -> None:
            calls.append('rpc-admission-close')

    class FakeHttpApiRateLimitPolicyManager:
        async def start(self) -> None:
            calls.append('http-rate-policy-start')

        async def close(self) -> None:
            calls.append('http-rate-policy-close')

    class FakeHttpApiAdmissionManager:
        async def start(self) -> None:
            calls.append('http-admission-start')

        async def close(self, *, drain_seconds: float) -> None:
            calls.append('http-admission-close')

    @asynccontextmanager
    async def fake_open_runtime_clients() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(redis=object(), shared_http_client=object())

    @asynccontextmanager
    async def fake_register_tortoise(*_args: object, **_kwargs: object) -> AsyncIterator[None]:
        yield

    async def no_op_async(*_args: object, **_kwargs: object) -> None:
        return None

    def bind_redis(*_args: object) -> None:
        calls.append('redis')

    def init_managers(app: FastAPI, *_args: object) -> None:
        calls.append('managers')
        app.state.health_dispatcher = FakeHealthDispatcher()
        app.state.circuit_manager = FakeCircuitManager()
        app.state.tip_dispatcher = FakeTipDispatcher()
        app.state.usage_recorder = FakeUsageRecorder()
        app.state.system_jsonrpc_cache_manager = None
        app.state.jsonrpc_rate_limit_policy_manager = FakeJsonRpcRateLimitPolicyManager()
        app.state.jsonrpc_admission_manager = FakeJsonRpcAdmissionManager()
        app.state.http_api_rate_limit_policy_manager = FakeHttpApiRateLimitPolicyManager()
        app.state.http_api_admission_manager = FakeHttpApiAdmissionManager()

    monkeypatch.setattr(lifespan_module.runtime, 'open_runtime_clients', fake_open_runtime_clients)
    monkeypatch.setattr(lifespan_module.service_state, 'bind_redis', bind_redis)
    monkeypatch.setattr(lifespan_module.service_state, 'init_managers', init_managers)
    monkeypatch.setattr(lifespan_module.service_state, 'close_runtime_state', no_op_async)
    monkeypatch.setattr(lifespan_module, 'init_cache', lambda *_args: None)
    monkeypatch.setattr(lifespan_module.broker, 'startup', no_op_async)
    monkeypatch.setattr(lifespan_module.broker, 'shutdown', no_op_async)
    monkeypatch.setattr(lifespan_module, 'RegisterTortoise', fake_register_tortoise)

    async with lifespan_module.lifespan(FastAPI()):
        pass

    assert calls == [
        'redis',
        'managers',
        'rate-policy-start',
        'rpc-admission-start',
        'http-rate-policy-start',
        'http-admission-start',
        'health-start',
        'circuit-start',
        'tip-start',
        'usage-start',
        'usage-close',
        'tip-close',
        'circuit-close',
        'health-close',
        'http-admission-close',
        'http-rate-policy-close',
        'rpc-admission-close',
        'rate-policy-close',
    ]
