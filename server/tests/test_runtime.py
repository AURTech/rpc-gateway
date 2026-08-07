import pytest
from app.infra import runtime


class _FailingRedis:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        return False

    async def aclose(self) -> None:
        self.closed = True


class _HealthyRedis:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_create_redis_client_closes_client_when_ping_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FailingRedis()
    kwargs: dict[str, object] = {}

    def fake_from_url(**values: object) -> _FailingRedis:
        kwargs.update(values)
        return redis

    monkeypatch.setattr(runtime.Redis, 'from_url', fake_from_url)

    with pytest.raises(SystemError, match='Redis init error.'):
        await runtime.create_redis_client()

    assert redis.closed is True
    assert kwargs['socket_connect_timeout'] == runtime.CONF.REDIS_CONNECT_TIMEOUT_SECONDS
    assert kwargs['socket_timeout'] == runtime.CONF.REDIS_SOCKET_TIMEOUT_SECONDS


@pytest.mark.anyio
async def test_open_runtime_clients_closes_redis_when_http_client_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _HealthyRedis()

    def fail_http_client() -> None:
        raise RuntimeError('http unavailable')

    monkeypatch.setattr(runtime.Redis, 'from_url', lambda **_kwargs: redis)
    monkeypatch.setattr(runtime, 'build_shared_http_client', fail_http_client)

    with pytest.raises(RuntimeError, match='http unavailable'):
        async with runtime.open_runtime_clients():
            pass

    assert redis.closed is True


@pytest.mark.anyio
async def test_open_runtime_clients_closes_clients_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _HealthyRedis()

    monkeypatch.setattr(runtime.Redis, 'from_url', lambda **_kwargs: redis)

    async with runtime.open_runtime_clients() as clients:
        http_client = clients.shared_http_client
        assert redis.closed is False
        assert http_client.is_closed is False

    assert redis.closed is True
    assert http_client.is_closed is True
