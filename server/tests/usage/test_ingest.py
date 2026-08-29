from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from app.orm.usage import GatewayUsageCheckpoint
from app.services.usage.buffer import BufferedUsageEvent, GatewayUsageBatch, GatewayUsageBuffer
from app.services.usage.ingest import METHODS_PER_GATEWAY_HOUR, OTHER_METHOD, GatewayUsageIngestManager
from app.services.usage.store import GatewayUsageStore, UsageScope
from tests.usage.factories import make_event


def test_method_cardinality_overflow_keeps_gateway_totals() -> None:
    events = [
        BufferedUsageEvent(stream_id='1-0', event=make_event('a' * 32, 'new-method-a')),
        BufferedUsageEvent(stream_id='2-0', event=make_event('b' * 32, 'new-method-b', successful=False)),
    ]
    scope = GatewayUsageIngestManager._event_scope(events[0].event)
    known_methods = {scope: {f'method-{index}' for index in range(METHODS_PER_GATEWAY_HOUR)}}

    rows = GatewayUsageIngestManager._aggregate_rows(events, known_methods)

    assert len(rows.gateway_hourly) == 1
    gateway_values = next(iter(rows.gateway_hourly.values()))
    assert gateway_values.total_requests == 2
    assert gateway_values.successful_requests == 1
    assert len(rows.method_hourly) == 1
    key, values = next(iter(rows.method_hourly.items()))
    assert key[5] == OTHER_METHOD
    assert values.total_requests == 2
    assert values.successful_requests == 1
    assert values.failed_requests == 1
    assert values.total_request_bytes == 4
    assert values.total_response_bytes == 16
    assert values.cache_eligible_requests == 2
    assert values.cache_hit_requests == 1


def test_endpoint_attempts_are_counted_without_duplicating_gateway_requests() -> None:
    event = make_event(
        'd' * 32,
        route_id='route-1',
        attempted_endpoint_ids=('endpoint-1', 'endpoint-2'),
    )
    buffered = BufferedUsageEvent(stream_id='1-0', event=event)
    scope = GatewayUsageIngestManager._event_scope(event)

    rows = GatewayUsageIngestManager._aggregate_rows([buffered], {scope: set()})

    gateway = next(iter(rows.gateway_hourly.values()))
    assert gateway.total_requests == 1
    assert sum(item.total_attempts for item in rows.endpoint_hourly.values()) == 2
    assert sum(item.first_attempts for item in rows.endpoint_hourly.values()) == 1
    assert sum(item.retry_attempts for item in rows.endpoint_hourly.values()) == 1
    assert {key[4] for key in rows.endpoint_hourly} == {'endpoint-1', 'endpoint-2'}
    route = next(iter(rows.route_hourly.values()))
    assert route.routed_requests == 1
    assert route.successful_requests == 1
    assert route.total_attempts == 2
    assert route.multi_attempt_requests == 1
    assert route.exhausted_requests == 0


def test_failed_routed_request_records_exhaustion_after_attempts() -> None:
    event = make_event(
        'e' * 32,
        successful=False,
        route_id='route-1',
        attempted_endpoint_ids=('endpoint-1', 'endpoint-2'),
    )
    buffered = BufferedUsageEvent(stream_id='1-0', event=event)
    scope = GatewayUsageIngestManager._event_scope(event)

    rows = GatewayUsageIngestManager._aggregate_rows([buffered], {scope: set()})

    route = next(iter(rows.route_hourly.values()))
    assert route.failed_requests == 1
    assert route.exhausted_requests == 1


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute_query_dict(self, query: str, values: list[Any] | None = None) -> list[dict[str, Any]]:
        del values
        self.statements.append(query)
        if 'FOR UPDATE' in query:
            return [{'last_stream_id': '0-0'}]
        return []

    async def execute_query(self, query: str, values: list[Any] | None = None) -> tuple[int, list[Any]]:
        del values
        self.statements.append(query)
        return 1, []


@pytest.mark.anyio
async def test_batch_activates_route_aware_metrics_before_aggregate_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection()
    orm_statements: list[str] = []
    buffered = BufferedUsageEvent(
        stream_id='1-0',
        event=make_event('c' * 32, route_id='route-1', attempted_endpoint_ids=('endpoint-1',)),
    )
    batch = GatewayUsageBatch(events=[buffered], stream_ids=['1-0'], last_stream_id='1-0', invalid=0)

    @asynccontextmanager
    async def transaction() -> AsyncGenerator[_Connection]:
        yield connection

    async def read_batch(*, after_id: str, count: int) -> GatewayUsageBatch:
        del after_id, count
        return batch

    async def delete(_stream_ids: list[str]) -> int:
        return 1

    async def delete_checkpointed(*, checkpoint: str, count: int) -> int:
        del checkpoint, count
        return 0

    async def lock_checkpoint(_connection: object) -> GatewayUsageCheckpoint:
        orm_statements.append('lock checkpoint')
        return GatewayUsageCheckpoint(id='usage-v3-checkpoint', last_stream_id='0-0')

    async def get_known_methods(
        _connection: object,
        scopes: set[UsageScope],
        *,
        excluded_method: str,
    ) -> dict[UsageScope, set[str]]:
        del excluded_method
        orm_statements.append('read methods')
        return {scope: set() for scope in scopes}

    async def update_checkpoint(
        _connection: object,
        _checkpoint: GatewayUsageCheckpoint,
        _stream_id: str,
    ) -> None:
        orm_statements.append('update checkpoint')

    monkeypatch.setattr('app.services.usage.ingest.in_tx', transaction)
    monkeypatch.setattr(GatewayUsageBuffer, 'read_batch', read_batch)
    monkeypatch.setattr(GatewayUsageBuffer, 'delete', delete)
    monkeypatch.setattr(GatewayUsageBuffer, 'delete_checkpointed', delete_checkpointed)
    monkeypatch.setattr(GatewayUsageStore, 'lock_checkpoint', lock_checkpoint)
    monkeypatch.setattr(GatewayUsageStore, 'get_known_methods', get_known_methods)
    monkeypatch.setattr(GatewayUsageStore, 'update_checkpoint', update_checkpoint)

    result = await GatewayUsageIngestManager._flush_batch(count=500)

    assert result == (1, 1, 1, 1, 0)
    assert len(connection.statements) + len(orm_statements) == 12
    activation_index = next(
        index for index, statement in enumerate(connection.statements) if 'gateway_usage_metric_availability' in statement
    )
    endpoint_index = next(
        index for index, statement in enumerate(connection.statements) if 'gateway_usage_endpoint_five_minute' in statement
    )
    route_index = next(
        index for index, statement in enumerate(connection.statements) if 'gateway_usage_route_five_minute' in statement
    )
    assert activation_index < endpoint_index
    assert activation_index < route_index
