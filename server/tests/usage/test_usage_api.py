from datetime import UTC, datetime, timedelta

import pytest
from app.model.blockchain import Chain
from app.orm.account import Account
from app.orm.application import App
from app.orm.jsonrpc_route import JsonRpcRoute
from app.orm.usage import (
    GatewayUsageEndpointHourly,
    GatewayUsageFiveMinute,
    GatewayUsageHourly,
    GatewayUsageMethodFiveMinute,
    GatewayUsageMetricAvailability,
    GatewayUsageRouteHourly,
)
from app.util.datetime import floor_utc_five_minutes, floor_utc_hour
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response
from tests.usage.factories import create_gateway, create_hourly_usage, point_total

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


@pytest.mark.anyio
async def test_endpoint_usage_is_scoped_to_owned_route(client: AsyncClient) -> None:
    await Account.create(email='endpoint-usage@example.com')
    await login_with_google(client, 'endpoint-usage@example.com', sub='endpoint-usage-sub')
    account = await Account.get(email='endpoint-usage@example.com')
    app = await App.create(account_id=account.id, name='Endpoint usage app')
    gateway = await create_gateway(app.id, chain=Chain.ETHEREUM)
    route = await JsonRpcRoute.create(gateway_id=gateway.id)
    bucket_hour = floor_utc_hour(datetime.now(UTC) - timedelta(hours=1))
    await GatewayUsageEndpointHourly.bulk_create(
        [
            GatewayUsageEndpointHourly(
                account_id=account.id,
                app_id=app.id,
                gateway_id=gateway.id,
                route_id=route.id,
                endpoint_id='endpoint-1',
                chain=gateway.chain,
                network=gateway.network,
                bucket_hour=bucket_hour,
                total_attempts=8,
                first_attempts=5,
                retry_attempts=2,
            ),
            GatewayUsageEndpointHourly(
                account_id=account.id,
                app_id=app.id,
                gateway_id=gateway.id,
                route_id=route.id,
                endpoint_id='endpoint-2',
                chain=gateway.chain,
                network=gateway.network,
                bucket_hour=bucket_hour,
                total_attempts=3,
                first_attempts=2,
                retry_attempts=1,
            ),
        ]
    )

    response = await client.get(
        '/v2/usage/endpoints',
        params={'time_range': 'daily', 'gateway_id': gateway.id, 'route_id': route.id, 'limit': 1},
    )
    data = assert_ok_response(response)['data']

    assert data['total_attempts'] == 11
    assert data['first_attempts'] == 7
    assert data['retry_attempts'] == 3
    assert data['unclassified_attempts'] == 1
    assert data['observed_endpoint_count'] == 2
    assert data['classification_coverage_start_at'] is None
    assert not data['classification_coverage_complete']
    assert data['granularity'] == 'hourly'
    assert [
        (
            item['endpoint_id'],
            item['total_attempts'],
            item['first_attempts'],
            item['retry_attempts'],
            item['unclassified_attempts'],
        )
        for item in data['items']
    ] == [('endpoint-1', 8, 5, 2, 1)]
    assert [sum(point['total_attempts'] for point in item['points']) for item in data['items']] == [8]
    assert [sum(point['first_attempts'] for point in item['points']) for item in data['items']] == [5]
    assert [sum(point['retry_attempts'] for point in item['points']) for item in data['items']] == [2]
    assert [sum(point['unclassified_attempts'] for point in item['points']) for item in data['items']] == [1]
    assert data['other_total_attempts'] == 3
    assert data['other_first_attempts'] == 2
    assert data['other_retry_attempts'] == 1
    assert data['other_unclassified_attempts'] == 0
    missing = await client.get(
        '/v2/usage/endpoints',
        params={'time_range': 'daily', 'gateway_id': gateway.id, 'route_id': 'not-owned'},
    )
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_route_usage_is_ranked_and_scoped_to_owned_app(client: AsyncClient) -> None:
    await Account.create(email='route-usage@example.com')
    await login_with_google(client, 'route-usage@example.com', sub='route-usage-sub')
    account = await Account.get(email='route-usage@example.com')
    await GatewayUsageMetricAvailability.filter(metric='route_usage').update(coverage_start_at=datetime.now(UTC))
    app = await App.create(account_id=account.id, name='Route usage app')
    gateway = await create_gateway(app.id, chain=Chain.ETHEREUM)
    first_route = await JsonRpcRoute.create(gateway_id=gateway.id)
    second_route = await JsonRpcRoute.create(gateway_id=gateway.id)
    bucket_hour = floor_utc_hour(datetime.now(UTC) - timedelta(hours=1))
    await GatewayUsageRouteHourly.bulk_create(
        [
            GatewayUsageRouteHourly(
                account_id=account.id,
                app_id=app.id,
                gateway_id=gateway.id,
                route_id=first_route.id,
                chain=gateway.chain,
                network=gateway.network,
                bucket_hour=bucket_hour,
                routed_requests=2,
                successful_requests=2,
                total_duration_ms=20,
                total_attempts=2,
            ),
            GatewayUsageRouteHourly(
                account_id=account.id,
                app_id=app.id,
                gateway_id=gateway.id,
                route_id=second_route.id,
                chain=gateway.chain,
                network=gateway.network,
                bucket_hour=bucket_hour,
                routed_requests=4,
                successful_requests=3,
                failed_requests=1,
                total_duration_ms=80,
                total_attempts=7,
                multi_attempt_requests=2,
                exhausted_requests=1,
            ),
        ]
    )

    response = await client.get(
        '/v2/usage/routes',
        params={'time_range': 'daily', 'app_id': app.id, 'gateway_id': gateway.id},
    )
    data = assert_ok_response(response)['data']

    assert [item['route_id'] for item in data['items']] == [second_route.id, first_route.id]
    assert isinstance(data['coverage_start_at'], str)
    assert not data['coverage_complete']
    ranked = data['items'][0]
    assert ranked['routed_requests'] == 4
    assert ranked['success_rate'] == 0.75
    assert ranked['avg_duration_ms'] == 20
    assert ranked['avg_attempts'] == 1.75
    assert ranked['multi_attempt_rate'] == 0.5
    assert ranked['exhausted_rate'] == 1
    assert sum(point['routed_requests'] for point in ranked['points']) == 4
    assert (await client.get('/v2/usage/routes', params={'app_id': 'not-owned'})).status_code == 404
    assert (await client.get('/v2/usage/routes')).status_code == 422


@pytest.mark.anyio
async def test_usage_endpoints_share_scope_filters_and_account_isolation(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')
    account = await Account.get(email='member@example.com')
    app = await App.create(account_id=account.id, name='Member app')
    ethereum = await create_gateway(app.id, chain=Chain.ETHEREUM)
    polygon = await create_gateway(app.id, chain=Chain.POLYGON)
    await create_hourly_usage(
        account.id,
        app.id,
        ethereum,
        total_requests=5,
        methods={'eth_call': 4, 'eth_getBalance': 1},
        method_cache={'eth_getBalance': (1, 1)},
    )
    await create_hourly_usage(account.id, app.id, polygon, total_requests=3, methods={'eth_call': 3})

    other = await Account.create(email='other@example.com')
    other_app = await App.create(account_id=other.id, name='Other app')
    other_gateway = await create_gateway(other_app.id, chain=Chain.ETHEREUM)
    await create_hourly_usage(other.id, other_app.id, other_gateway, total_requests=99, methods={'eth_call': 99})

    params = {
        'time_range': 'daily',
        'app_id': app.id,
        'gateway_id': ethereum.id,
        'chain': 'ethereum',
        'network': 'mainnet',
    }
    summary = assert_ok_response(await client.get('/v2/usage/summary', params=params))['data']
    series = assert_ok_response(await client.get('/v2/usage/series', params=params))['data']
    methods = assert_ok_response(await client.get('/v2/usage/methods', params={**params, 'limit': 2}))['data']
    cache_methods = assert_ok_response(
        await client.get(
            '/v2/usage/methods',
            params={**params, 'rank_by': 'cache_eligible_requests', 'limit': 2},
        )
    )['data']
    networks = assert_ok_response(await client.get('/v2/usage/networks', params={**params, 'limit': 2}))['data']

    assert summary['total_requests'] == 5
    assert summary['data_through'] == summary['end_at']
    assert all(isinstance(data['data_through'], str) for data in (series, methods, networks))
    assert len(series['items']) == 24
    assert sum(point['total_requests'] for point in series['items']) == 5
    assert [(item['method'], point_total(item)) for item in methods['items']] == [
        ('eth_call', 4),
        ('eth_getBalance', 1),
    ]
    method_point = methods['items'][0]['points'][0]
    assert set(method_point) == {
        'bucket_start',
        'total_requests',
        'cache_eligible_requests',
        'cache_hit_requests',
        'cache_hit_rate',
    }
    assert [item['method'] for item in cache_methods['items']] == ['eth_getBalance']
    assert sum(point['cache_eligible_requests'] for point in cache_methods['items'][0]['points']) == 1
    assert sum(point['cache_hit_requests'] for point in cache_methods['items'][0]['points']) == 1
    assert [(item['chain'], item['network'], point_total(item)) for item in networks['items']] == [('ethereum', 'mainnet', 5)]
    assert set(networks['items'][0]['points'][0]) == {
        'bucket_start',
        'total_requests',
        'total_duration_ms',
        'avg_duration_ms',
        'cache_eligible_requests',
        'cache_hit_requests',
        'cache_hit_rate',
    }
    network_point = next(point for point in networks['items'][0]['points'] if point['total_requests'] > 0)
    assert network_point['avg_duration_ms'] == 10
    assert network_point['cache_hit_rate'] == 1
    bucket_start = floor_utc_five_minutes(datetime.now(UTC)) - timedelta(minutes=5)
    await GatewayUsageFiveMinute.create(
        account_id=account.id,
        app_id=app.id,
        gateway_id=ethereum.id,
        chain=ethereum.chain,
        network=ethereum.network,
        bucket_start=bucket_start,
        total_requests=2,
        successful_requests=2,
        total_duration_ms=20,
    )
    await GatewayUsageMethodFiveMinute.create(
        account_id=account.id,
        app_id=app.id,
        gateway_id=ethereum.id,
        chain=ethereum.chain,
        network=ethereum.network,
        method='eth_call',
        bucket_start=bucket_start,
        total_requests=2,
        successful_requests=2,
        total_duration_ms=20,
    )
    hourly_params = {**params, 'time_range': 'hourly'}
    hourly = assert_ok_response(await client.get('/v2/usage/series', params=hourly_params))['data']
    hourly_methods = assert_ok_response(await client.get('/v2/usage/methods', params=hourly_params))['data']
    hourly_networks = assert_ok_response(await client.get('/v2/usage/networks', params=hourly_params))['data']
    assert hourly['time_range'] == 'hourly'
    assert hourly['granularity'] == 'five_minute'
    assert all(isinstance(data['data_through'], str) for data in (hourly, hourly_methods, hourly_networks))
    assert len(hourly['items']) == 12
    assert sum(point['total_requests'] for point in hourly['items']) == 2
    assert point_total(hourly_methods['items'][0]) == 2
    assert point_total(hourly_networks['items'][0]) == 2
    assert (await client.get('/v2/usage/methods', params={'limit': 101})).status_code == 422
    assert (await client.get('/v2/usage/methods', params={'rank_by': 'latency'})).status_code == 422
    assert (await client.get('/v2/usage/gateways')).status_code == 404


@pytest.mark.anyio
async def test_usage_summary_compares_against_the_preceding_window(client: AsyncClient) -> None:
    await Account.create(email='compare-weekly@example.com')
    await login_with_google(client, 'compare-weekly@example.com', sub='compare-weekly-sub')
    account = await Account.get(email='compare-weekly@example.com')
    app = await App.create(account_id=account.id, name='Compare weekly app')
    gateway = await create_gateway(app.id, chain=Chain.ETHEREUM)
    midnight = floor_utc_hour(datetime.now(UTC)).replace(hour=0)
    buckets = {midnight - timedelta(days=2): 6, midnight - timedelta(days=9): 4, midnight - timedelta(days=20): 99}
    for bucket_hour, total_requests in buckets.items():
        await GatewayUsageHourly.create(
            account_id=account.id,
            app_id=app.id,
            gateway_id=gateway.id,
            chain=gateway.chain,
            network=gateway.network,
            bucket_hour=bucket_hour,
            total_requests=total_requests,
            successful_requests=total_requests,
            total_duration_ms=total_requests * 10,
            cache_eligible_requests=total_requests,
            cache_hit_requests=total_requests,
        )

    params = {'time_range': 'weekly'}
    plain = assert_ok_response(await client.get('/v2/usage/summary', params=params))['data']
    summary = assert_ok_response(await client.get('/v2/usage/summary', params={**params, 'compare': 'true'}))['data']
    previous = summary['previous']

    assert plain['previous'] is None
    assert summary['total_requests'] == 6
    assert previous['total_requests'] == 4
    assert previous['end_at'] == summary['start_at']
    start_at = datetime.fromisoformat(summary['start_at'])
    end_at = datetime.fromisoformat(summary['end_at'])
    previous_start_at = datetime.fromisoformat(previous['start_at'])
    assert end_at - start_at == start_at - previous_start_at
    assert previous['avg_duration_ms'] == 10
    assert previous['cache_hit_rate'] == 1


@pytest.mark.anyio
async def test_hourly_usage_summary_compares_fine_buckets(client: AsyncClient) -> None:
    await Account.create(email='compare-hourly@example.com')
    await login_with_google(client, 'compare-hourly@example.com', sub='compare-hourly-sub')
    account = await Account.get(email='compare-hourly@example.com')
    app = await App.create(account_id=account.id, name='Compare hourly app')
    gateway = await create_gateway(app.id, chain=Chain.ETHEREUM)
    latest = floor_utc_five_minutes(datetime.now(UTC))
    buckets = {latest - timedelta(minutes=5): 3, latest - timedelta(minutes=65): 7, latest - timedelta(minutes=185): 50}
    for bucket_start, total_requests in buckets.items():
        await GatewayUsageFiveMinute.create(
            account_id=account.id,
            app_id=app.id,
            gateway_id=gateway.id,
            chain=gateway.chain,
            network=gateway.network,
            bucket_start=bucket_start,
            total_requests=total_requests,
            successful_requests=total_requests,
            total_duration_ms=total_requests * 10,
        )

    summary = assert_ok_response(await client.get('/v2/usage/summary', params={'time_range': 'hourly', 'compare': 'true'}))[
        'data'
    ]

    assert summary['total_requests'] == 3
    assert summary['previous']['total_requests'] == 7
    assert summary['previous']['end_at'] == summary['start_at']
