from types import SimpleNamespace
from typing import Any

import pytest
from app.infra import db as db_module
from app.model.blockchain import Chain, Network
from app.model.system_cache import CacheKey, CachePolicy, CacheTier
from app.model.transport import Transport
from app.services.system_cache import flight as flight_module
from app.services.system_cache import store as store_module
from app.services.system_cache.flight import PostgresRetentionFlight
from app.services.system_cache.store import PostgresRetentionStore


class _Connection:
    async def execute_query_dict(self, *_args: object, **_kwargs: object) -> list[dict[str, Any]]:
        return []


class _Connections:
    def __init__(self, connection: _Connection, requested: list[str]) -> None:
        self._connection = connection
        self._requested = requested

    def get(self, name: str) -> _Connection:
        self._requested.append(name)
        return self._connection


def _policy() -> CachePolicy:
    return CachePolicy(
        key=CacheKey(
            transport=Transport.JSONRPC,
            chain=Chain.ARBITRUM,
            network=Network.MAINNET,
            operation='debug_traceBlockByNumber',
            digest='a' * 40,
        ),
        tier=CacheTier.POSTGRES_RETENTION,
        retention_seconds=300,
        ttl_ms=None,
        sequence=1,
    )


def test_business_transaction_uses_active_context_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    transaction = object()

    def start_transaction(*, connection_name: str) -> object:
        requested.append(connection_name)
        return transaction

    context = SimpleNamespace(default_connection='isolated-business')
    monkeypatch.setattr(db_module, 'get_current_context', lambda: context)
    monkeypatch.setattr(db_module, 'in_transaction', start_transaction)

    assert db_module.in_tx() is transaction
    assert requested == ['isolated-business']


def test_business_transaction_falls_back_to_default_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    transaction = object()

    def start_transaction(*, connection_name: str) -> object:
        requested.append(connection_name)
        return transaction

    monkeypatch.setattr(db_module, 'get_current_context', lambda: None)
    monkeypatch.setattr(db_module, 'in_transaction', start_transaction)

    assert db_module.in_tx() is transaction
    assert requested == ['default']


@pytest.mark.anyio
async def test_retention_store_uses_selected_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    connection = _Connection()
    monkeypatch.setattr(store_module, 'connections', _Connections(connection, requested))

    assert await PostgresRetentionStore('cache-retention').get(_policy()) is None
    assert requested == ['cache-retention']


@pytest.mark.anyio
async def test_retention_coordination_uses_selected_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    connection = _Connection()
    monkeypatch.setattr(flight_module, 'connections', _Connections(connection, requested))

    lease = await PostgresRetentionFlight(lease_ms=1000, connection_name='cache-coordination').acquire(_policy().key)
    assert lease is None
    assert requested == ['cache-coordination']
