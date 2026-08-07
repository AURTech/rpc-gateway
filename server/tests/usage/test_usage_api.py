from datetime import UTC, datetime, timedelta

import pytest
from app.model.blockchain import Chain
from app.orm.account import Account
from app.orm.application import App
from app.orm.usage import GatewayUsageFiveMinute, GatewayUsageMethodFiveMinute
from app.util.datetime import floor_utc_five_minutes
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response
from tests.usage.factories import create_gateway, create_hourly_usage, point_total

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


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
