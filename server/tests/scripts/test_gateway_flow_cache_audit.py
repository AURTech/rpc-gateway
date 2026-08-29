import base64
from collections.abc import AsyncIterator

import asyncpg
import orjson
import pytest
from app.infra import redis as redis_keys
from app.model.blockchain import Chain, Network
from app.model.transport import Transport
from app.services.system_cache.key import build_cache_key
from redis.asyncio import Redis
from scripts.gateway_flow_integration.inspector import (
    PostgresRetentionAuditSpec,
    RedisTtlAuditSpec,
    RuntimeInspector,
    _redis_ttl_key,
)
from scripts.gateway_flow_integration.scenario import _cache_digest


class _Connection:
    def __init__(self) -> None:
        self.query = ''
        self.args: tuple[object, ...] = ()

    async def fetchval(self, query: str, *args: object) -> int:
        self.query = query
        self.args = args
        return 0

    async def fetch(self, query: str) -> list[object]:
        self.query = query
        return []

    async def close(self) -> None:
        pass


class _Redis:
    def __init__(self, keys: tuple[str, ...] = (), values: tuple[bytes, ...] = ()) -> None:
        self._keys = keys
        self._values = values

    async def scan_iter(self, *, match: str, count: int) -> AsyncIterator[object]:
        del count
        keys = self._keys if ':redis_ttl:' in match else ()
        for key in keys:
            yield key

    async def mget(self, keys: list[str]) -> list[object]:
        assert keys == list(self._keys)
        return list(self._values)

    async def pttl(self, key: str) -> int:
        assert key in self._keys
        return 1000

    async def aclose(self) -> None:
        pass


def test_gateway_flow_cache_digest_matches_runtime_identity() -> None:
    operation = 'eth_blockNumber'
    identity = 'finalized'

    runtime_key = build_cache_key(
        transport=Transport.JSONRPC,
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        operation=operation,
        identity=identity,
    )

    assert _cache_digest(operation, identity) == runtime_key.digest


def test_gateway_flow_redis_key_includes_transport() -> None:
    spec = RedisTtlAuditSpec(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='eth_blockNumber',
        expected_cache_key='digest',
        expected_result='0x1',
    )

    assert _redis_ttl_key(spec) == redis_keys.build_key(
        'system_cache',
        'v1',
        'redis_ttl',
        Transport.JSONRPC.value,
        Chain.ETHEREUM.value,
        Network.MAINNET.value,
        'eth_blockNumber',
        'digest',
    )


@pytest.mark.anyio
async def test_gateway_flow_retention_query_uses_transport_and_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection()

    async def connect(postgres_url: str) -> _Connection:
        assert postgres_url == 'postgres://audit.test/cache'
        return connection

    monkeypatch.setattr(asyncpg, 'connect', connect)
    inspector = RuntimeInspector('redis://audit.test/0', 'postgres://audit.test/cache')
    spec = PostgresRetentionAuditSpec(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='eth_getBlockByNumber',
        expected_cache_key='digest',
        expected_sequence=1,
        expected_result={},
    )

    try:
        await inspector.audit_postgres_retention_absent(spec)
    finally:
        await inspector.close()

    query = ' '.join(connection.query.split())
    assert 'transport = $1' in query
    assert 'operation = $4' in query
    assert 'method' not in query
    assert connection.args == (
        Transport.JSONRPC.value,
        Chain.ETHEREUM.value,
        Network.MAINNET.value,
        'eth_getBlockByNumber',
        'digest',
    )


@pytest.mark.anyio
async def test_gateway_flow_retention_rows_use_transport_and_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection()
    redis_spec = RedisTtlAuditSpec(
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='eth_blockNumber',
        expected_cache_key='digest',
        expected_result='0x1',
    )
    redis_key = _redis_ttl_key(redis_spec)
    redis_value = orjson.dumps(
        {
            'publisher_fence': 1,
            'payload': base64.b64encode(orjson.dumps(redis_spec.expected_result)).decode(),
        }
    )

    async def connect(postgres_url: str) -> _Connection:
        assert postgres_url == 'postgres://audit.test/cache'
        return connection

    def redis_from_url(url: str, *, decode_responses: bool, retry_on_timeout: bool) -> _Redis:
        assert url == 'redis://audit.test/0'
        assert decode_responses
        assert not retry_on_timeout
        return _Redis((redis_key,), (redis_value,))

    monkeypatch.setattr(asyncpg, 'connect', connect)
    monkeypatch.setattr(Redis, 'from_url', staticmethod(redis_from_url))
    inspector = RuntimeInspector('redis://audit.test/0', 'postgres://audit.test/cache')

    try:
        result = await inspector.audit_cache([], [redis_spec])
    finally:
        await inspector.close()

    query = ' '.join(connection.query.split())
    assert 'SELECT transport, chain, network, operation, cache_key' in query
    assert 'method' not in query
    assert result['postgres_retention'] == []
