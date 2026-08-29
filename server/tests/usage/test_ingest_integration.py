from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import CONF
from app.model.blockchain import Chain, Network
from app.orm.usage import (
    GatewayUsageCheckpoint,
    GatewayUsageEndpointFiveMinute,
    GatewayUsageEndpointHourly,
    GatewayUsageFiveMinute,
    GatewayUsageHourly,
    GatewayUsageMethodFiveMinute,
    GatewayUsageMethodHourly,
    GatewayUsageMetricAvailability,
    GatewayUsageRollupHour,
    GatewayUsageRouteFiveMinute,
    GatewayUsageRouteHourly,
)
from app.services.base import Manager
from app.services.usage.buffer import GatewayUsageBuffer
from app.services.usage.ingest import GatewayUsageDrainResult, GatewayUsageIngestManager
from app.services.usage.rollup import GatewayUsageRollupManager
from app.services.usage.store import EndpointUsageAggregate, GatewayUsageStore, UsageEndpointKey
from fastapi import FastAPI
from redis.asyncio import Redis
from tests.infra import build_test_orm_config, create_schema, drop_schema
from tests.usage.factories import make_event
from tortoise import Tortoise, connections


async def _drain() -> GatewayUsageDrainResult:
    return await GatewayUsageIngestManager.drain(
        batch_size=500,
        max_batches=20,
        max_seconds=5,
        lease_seconds=30,
    )


@pytest.fixture
async def orm_usage_schema(test_redis: Redis) -> AsyncGenerator[None]:
    schema = f'test_{uuid4().hex}'
    await create_schema(schema)
    try:
        await Tortoise.init(config=build_test_orm_config(schema))
        await Tortoise.generate_schemas(safe=False)
        await GatewayUsageMetricAvailability.bulk_create(
            [
                GatewayUsageMetricAvailability(metric='route_usage'),
                GatewayUsageMetricAvailability(metric='endpoint_attempt_classification'),
            ]
        )
        Manager.set_redis(test_redis)
        yield
    finally:
        Manager.clear_redis()
        await Tortoise.close_connections()
        await drop_schema(schema)


@pytest.mark.anyio
async def test_fresh_orm_schema_can_drain_usage(orm_usage_schema: None) -> None:
    del orm_usage_schema
    await GatewayUsageBuffer.append(make_event('c' * 32))
    before = datetime.now(UTC)

    result = await _drain()

    after = datetime.now(UTC)
    assert result['inserted'] == 1
    assert result['remaining_entries'] == 0
    checkpoint = await GatewayUsageCheckpoint.get(id='usage-v3-checkpoint')
    assert checkpoint.last_stream_id != '0-0'
    aggregate = await GatewayUsageHourly.get()
    method = await GatewayUsageMethodHourly.get()
    fine_aggregate = await GatewayUsageFiveMinute.get()
    fine_method = await GatewayUsageMethodFiveMinute.get()
    availability = {row.metric: row.coverage_start_at for row in await GatewayUsageMetricAvailability.all()}
    assert set(availability) == {'route_usage', 'endpoint_attempt_classification'}
    assert all(value is not None and before <= value <= after for value in availability.values())
    assert len(set(availability.values())) == 1
    assert aggregate.total_requests == 1
    assert method.total_requests == 1
    assert fine_aggregate.total_requests == 1
    assert fine_method.total_requests == 1

    await GatewayUsageBuffer.append(make_event('f' * 32))
    await _drain()

    unchanged = {row.metric: row.coverage_start_at for row in await GatewayUsageMetricAvailability.all()}
    assert unchanged == availability


@pytest.mark.anyio
async def test_new_endpoint_attempts_classify_mixed_historical_buckets(orm_usage_schema: None) -> None:
    del orm_usage_schema
    bucket = datetime(2026, 8, 26, 1, tzinfo=UTC)
    await GatewayUsageEndpointFiveMinute.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        route_id='route-1',
        endpoint_id='endpoint-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        bucket_start=bucket,
        total_attempts=5,
    )
    await GatewayUsageEndpointHourly.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        route_id='route-1',
        endpoint_id='endpoint-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        bucket_hour=bucket,
        total_attempts=5,
    )
    key: UsageEndpointKey = (
        'account-1',
        'app-1',
        'gateway-1',
        'route-1',
        'endpoint-1',
        Chain.ETHEREUM.value,
        Network.MAINNET.value,
        bucket,
    )
    values: dict[UsageEndpointKey, EndpointUsageAggregate] = {
        key: EndpointUsageAggregate(total_attempts=2, first_attempts=1, retry_attempts=1)
    }
    connection = connections.get('default')

    await GatewayUsageStore.upsert_endpoint_fine(connection, values)
    await GatewayUsageStore.upsert_endpoint_hourly(connection, values)

    fine = await GatewayUsageEndpointFiveMinute.get()
    hourly = await GatewayUsageEndpointHourly.get()
    assert (fine.total_attempts, fine.first_attempts, fine.retry_attempts) == (7, 1, 1)
    assert (hourly.total_attempts, hourly.first_attempts, hourly.retry_attempts) == (7, 1, 1)


@pytest.mark.anyio
async def test_cutover_rolls_fine_usage_into_hourly_rows(
    orm_usage_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del orm_usage_schema
    monkeypatch.setattr(CONF, 'USAGE_ASYNC_ROLLUP_CUTOVER_AT', datetime(2026, 1, 1, tzinfo=UTC))
    await GatewayUsageBuffer.append(
        make_event('d' * 32, route_id='route-1', attempted_endpoint_ids=('endpoint-1', 'endpoint-2'))
    )
    await GatewayUsageBuffer.append(
        make_event(
            'e' * 32,
            successful=False,
            route_id='route-1',
            attempted_endpoint_ids=('endpoint-1', 'endpoint-2'),
        )
    )

    drain = await _drain()

    assert drain['inserted'] == 2
    assert await GatewayUsageHourly.all().count() == 0
    assert await GatewayUsageMethodHourly.all().count() == 0
    assert (await GatewayUsageFiveMinute.get()).total_requests == 2
    assert (await GatewayUsageMethodFiveMinute.get()).total_requests == 2
    fine_route = await GatewayUsageRouteFiveMinute.get()
    assert fine_route.routed_requests == 2
    assert fine_route.total_attempts == 4
    assert fine_route.multi_attempt_requests == 2
    assert fine_route.exhausted_requests == 1
    fine_endpoints = {row.endpoint_id: row for row in await GatewayUsageEndpointFiveMinute.all()}
    assert fine_endpoints['endpoint-1'].first_attempts == 2
    assert fine_endpoints['endpoint-1'].retry_attempts == 0
    assert fine_endpoints['endpoint-2'].first_attempts == 0
    assert fine_endpoints['endpoint-2'].retry_attempts == 2
    assert await GatewayUsageRollupHour.all().count() == 1

    rollup = await GatewayUsageRollupManager.rollup(limit=24, lease_seconds=30)

    assert rollup == {'lock_acquired': True, 'rolled_hours': 1}
    assert (await GatewayUsageHourly.get()).total_requests == 2
    assert (await GatewayUsageMethodHourly.get()).total_requests == 2
    route = await GatewayUsageRouteHourly.get()
    assert route.routed_requests == 2
    assert route.exhausted_requests == 1
    endpoints = {row.endpoint_id: row for row in await GatewayUsageEndpointHourly.all()}
    assert endpoints['endpoint-1'].first_attempts == 2
    assert endpoints['endpoint-2'].retry_attempts == 2
    assert await GatewayUsageRollupHour.all().count() == 0


@pytest.mark.anyio
async def test_fresh_orm_schema_removes_expired_usage(
    orm_usage_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del orm_usage_schema
    monkeypatch.setattr(CONF, 'USAGE_HOURLY_RETENTION_MONTHS', 3)
    monkeypatch.setattr(CONF, 'USAGE_FINE_RETENTION_HOURS', 48)
    expired_at = datetime(2026, 4, 30, 23, tzinfo=UTC)
    retained_at = datetime(2026, 5, 1, tzinfo=UTC)
    reference_at = datetime(2026, 7, 24, tzinfo=UTC)
    expired_gateway = await GatewayUsageHourly.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        bucket_hour=expired_at,
        total_requests=1,
        successful_requests=1,
    )
    retained_gateway = await GatewayUsageHourly.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        bucket_hour=retained_at,
        total_requests=1,
        successful_requests=1,
    )
    expired_method = await GatewayUsageMethodHourly.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='eth_call',
        bucket_hour=expired_at,
        total_requests=1,
        successful_requests=1,
    )
    retained_method = await GatewayUsageMethodHourly.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='eth_call',
        bucket_hour=retained_at,
        total_requests=1,
        successful_requests=1,
    )
    expired_fine = await GatewayUsageFiveMinute.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        bucket_start=reference_at - timedelta(hours=49),
        total_requests=1,
        successful_requests=1,
    )
    retained_fine = await GatewayUsageFiveMinute.create(
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        bucket_start=reference_at - timedelta(hours=47),
        total_requests=1,
        successful_requests=1,
    )

    result = await GatewayUsageIngestManager.maintain_partitions(now=reference_at)

    assert result.created_partitions == 0
    assert result.dropped_partitions == 0
    assert result.deleted_gateway_rows == 1
    assert result.deleted_method_rows == 1
    assert result.deleted_fine_gateway_rows == 1
    assert not await GatewayUsageHourly.filter(id=expired_gateway.id).exists()
    assert await GatewayUsageHourly.filter(id=retained_gateway.id).exists()
    assert not await GatewayUsageMethodHourly.filter(id=expired_method.id).exists()
    assert await GatewayUsageMethodHourly.filter(id=retained_method.id).exists()
    assert not await GatewayUsageFiveMinute.filter(id=expired_fine.id).exists()
    assert await GatewayUsageFiveMinute.filter(id=retained_fine.id).exists()


@pytest.mark.anyio
async def test_checkpoint_skips_replay_after_stream_delete_failure(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del app
    await GatewayUsageBuffer.append(make_event('a' * 32))

    async def fail_delete(_stream_ids: list[str]) -> int:
        raise ConnectionError('delete failed')

    with monkeypatch.context() as patch:
        patch.setattr(GatewayUsageBuffer, 'delete', fail_delete)
        first = await _drain()

    assert first['inserted'] == 1
    assert first['acknowledged'] == 0
    checkpoint = await GatewayUsageCheckpoint.get(id='usage-v3-checkpoint')
    assert checkpoint.last_stream_id != '0-0'

    second = await _drain()

    assert second['inserted'] == 0
    aggregate = await GatewayUsageHourly.get()
    method = await GatewayUsageMethodHourly.get()
    assert aggregate.total_requests == 1
    assert method.total_requests == 1
    assert await GatewayUsageBuffer.redis.xlen(GatewayUsageBuffer.stream_key()) == 0


@pytest.mark.anyio
async def test_invalid_event_advances_checkpoint(app: FastAPI) -> None:
    del app
    stream_id = await GatewayUsageBuffer.redis.xadd(GatewayUsageBuffer.stream_key(), {'payload': '{invalid'})

    result = await _drain()

    checkpoint = await GatewayUsageCheckpoint.get(id='usage-v3-checkpoint')
    assert result['invalid'] == 1
    assert result['inserted'] == 0
    assert checkpoint.last_stream_id == str(stream_id)
    assert await GatewayUsageHourly.all().count() == 0
    assert await GatewayUsageFiveMinute.all().count() == 0
    assert all(row.coverage_start_at is not None for row in await GatewayUsageMetricAvailability.all())


@pytest.mark.anyio
async def test_store_failure_rolls_back_checkpoint_and_aggregates(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del app
    await GatewayUsageBuffer.append(make_event('b' * 32))

    async def fail_upsert(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError('store failed')

    with monkeypatch.context() as patch:
        patch.setattr(GatewayUsageStore, 'upsert_method_hourly', fail_upsert)
        with pytest.raises(RuntimeError, match='store failed'):
            await _drain()

    checkpoint = await GatewayUsageCheckpoint.get(id='usage-v3-checkpoint')
    assert checkpoint.last_stream_id == '0-0'
    assert await GatewayUsageHourly.all().count() == 0
    assert all(row.coverage_start_at is None for row in await GatewayUsageMetricAvailability.all())

    result = await _drain()

    assert result['inserted'] == 1
    assert await GatewayUsageHourly.all().count() == 1
    assert await GatewayUsageFiveMinute.all().count() == 1
    assert all(row.coverage_start_at is not None for row in await GatewayUsageMetricAvailability.all())
