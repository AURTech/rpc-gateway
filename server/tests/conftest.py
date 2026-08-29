from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from ipaddress import IPv4Address
from uuid import uuid4

import httpx
import pytest
from app import init_app
from app.clients.endpoint import EndpointHttpClient
from app.clients.transport import HttpTransport
from app.core.config import CONF
from app.infra.outbound_policy import OutboundTargetPolicy
from app.services.auth import AuthManager
from app.services.auth.password import PasswordWorker
from app.services.base import Manager
from app.services.endpoint import (
    EndpointAccessManager,
    EndpointHealthManager,
    EndpointManager,
    ManagedEndpointManager,
)
from app.services.endpoint.probe import EndpointProbeManager
from app.services.jsonrpc_route import DatabaseJsonRpcEndpointRouteReferenceLookup
from app.services.provider import ProviderManager
from app.services.runtime_state.endpoint.health import HealthManager
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis
from tests.auth.fixtures import configure_auth_settings, fake_google_exchange
from tests.helpers import asgi_client
from tests.infra import (
    build_test_orm_config,
    clear_test_redis_keys,
    configure_test_runtime,
    create_schema,
    drop_schema,
    migrate_schema,
    setup_test_redis,
    truncate_test_tables,
)
from tortoise import Tortoise
from tortoise.contrib.fastapi import RegisterTortoise

configure_test_runtime()


@pytest.fixture(scope='session', autouse=True)
def _test_runtime_guard() -> None:
    configure_test_runtime()


@pytest.fixture(scope='session')
def anyio_backend() -> str:
    return 'asyncio'


@pytest.fixture(autouse=True)
def outbound_target_policy_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    async def dns_lookup(_host: str, _port: int) -> tuple[IPv4Address, ...]:
        return (IPv4Address('93.184.216.34'),)

    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    monkeypatch.setattr('app.clients.provider.probe.build_outbound_target_policy', lambda: policy)
    monkeypatch.setattr('app.services.endpoint.endpoint.build_outbound_target_policy', lambda: policy)
    monkeypatch.setattr('app.services.endpoint.managed.build_outbound_target_policy', lambda: policy)


@pytest.fixture
async def test_redis() -> AsyncGenerator[Redis]:
    redis = Redis.from_url(url=CONF.TEST_REDIS_URL, decode_responses=True, retry_on_timeout=False)
    # Reason: redis.asyncio ping is awaitable at runtime; stubs are narrower here.
    if not await redis.ping():  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
        raise RuntimeError('Test Redis is not reachable.')
    await clear_test_redis_keys(redis)
    try:
        yield redis
    finally:
        await clear_test_redis_keys(redis)
        await redis.aclose()


@pytest.fixture(scope='session')
async def migrated_test_schema() -> AsyncGenerator[str]:
    schema = f'test_{uuid4().hex}'
    await create_schema(schema)
    try:
        await migrate_schema(schema)
        yield schema
    finally:
        await Tortoise.close_connections()
        await drop_schema(schema)


@asynccontextmanager
async def test_lifespan(app: FastAPI, schema: str) -> AsyncGenerator[None]:
    redis: Redis | None = None
    Manager.clear_redis()
    shared_http_client = httpx.AsyncClient()
    try:
        config = build_test_orm_config(schema)
        redis = await setup_test_redis(app)
        app.state.test_schema = schema
        app.state.shared_http_client = shared_http_client
        password_worker = PasswordWorker(max_concurrency=CONF.AUTH_PASSWORD_MAX_CONCURRENCY)
        transport = HttpTransport(shared_http_client)
        policy = OutboundTargetPolicy()
        endpoint_client = EndpointHttpClient(transport)
        health_manager = HealthManager(redis)
        probe_manager = EndpointProbeManager(
            http_client=endpoint_client,
            target_policy=policy,
            timeout_seconds=CONF.ENDPOINT_HEALTH_CHECK_TIMEOUT_SECONDS,
            max_response_bytes=CONF.ENDPOINT_HEALTH_CHECK_MAX_RESPONSE_BYTES,
        )
        app.state.auth_manager = AuthManager(http_client=shared_http_client, password_worker=password_worker)
        app.state.endpoint_access_manager = EndpointAccessManager(endpoint_client, policy)
        app.state.endpoint_health_manager = EndpointHealthManager(
            probe_manager=probe_manager,
            health_manager=health_manager,
        )
        route_references = DatabaseJsonRpcEndpointRouteReferenceLookup()
        app.state.endpoint_manager = EndpointManager(route_references)
        app.state.provider_manager = ProviderManager(transport, ManagedEndpointManager(route_references))
        async with RegisterTortoise(app, config=config, generate_schemas=False):
            yield
    finally:
        if redis is not None:
            await clear_test_redis_keys(redis)
            await redis.aclose()
        Manager.clear_redis()
        await Tortoise.close_connections()
        await shared_http_client.aclose()


@pytest.fixture
async def app(migrated_test_schema: str) -> AsyncGenerator[FastAPI]:
    await truncate_test_tables(migrated_test_schema)
    application = init_app(lifespan_fn=lambda app: test_lifespan(app, migrated_test_schema))
    try:
        async with LifespanManager(application, startup_timeout=30):
            yield application
    finally:
        await truncate_test_tables(migrated_test_schema)


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with asgi_client(app) as client:
        yield client


@pytest.fixture
async def shared_http_client() -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as http_client:
        yield http_client


@pytest.fixture
def auth_manager(shared_http_client: httpx.AsyncClient) -> AuthManager:
    password_worker = PasswordWorker(max_concurrency=CONF.AUTH_PASSWORD_MAX_CONCURRENCY)
    return AuthManager(http_client=shared_http_client, password_worker=password_worker)


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    return configure_auth_settings(monkeypatch)


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('app.services.auth.auth.AuthManager._fetch_google_profile', fake_google_exchange)
