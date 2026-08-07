import pytest
from app.model.blockchain import Chain
from app.orm.account import Account
from app.orm.application import App
from app.orm.gateway import Gateway
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response
from tests.usage.factories import create_gateway, create_hourly_usage, point_total

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


async def _seed_member_networks(client: AsyncClient) -> tuple[App, Gateway]:
    """Sign in a member owning one Ethereum and one Polygon gateway with 3 and 5 hourly requests."""
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')
    account = await Account.get(email='member@example.com')
    app = await App.create(account_id=account.id, name='Member app')
    ethereum = await create_gateway(app.id, chain=Chain.ETHEREUM)
    polygon = await create_gateway(app.id, chain=Chain.POLYGON)
    await create_hourly_usage(account.id, app.id, ethereum, total_requests=3)
    await create_hourly_usage(account.id, app.id, polygon, total_requests=5)
    return app, ethereum


@pytest.mark.anyio
async def test_networks_keep_chain_dimension(client: AsyncClient) -> None:
    await _seed_member_networks(client)
    other = await Account.create(email='other@example.com')
    other_app = await App.create(account_id=other.id, name='Other app')
    other_gateway = await create_gateway(other_app.id, chain=Chain.BSC)
    await create_hourly_usage(other.id, other_app.id, other_gateway, total_requests=9)

    response = await client.get('/v2/usage/networks', params={'time_range': 'daily'})

    data = assert_ok_response(response)['data']
    assert data['granularity'] == 'hourly'
    assert [(item['chain'], item['network']) for item in data['items']] == [
        ('polygon', 'mainnet'),
        ('ethereum', 'mainnet'),
    ]
    assert [item['chain_label'] for item in data['items']] == ['Polygon', 'Ethereum']
    assert [point_total(item) for item in data['items']] == [5, 3]
    assert all(len(item['points']) == 24 for item in data['items'])


@pytest.mark.anyio
async def test_networks_apply_scope_filters(client: AsyncClient) -> None:
    app, ethereum = await _seed_member_networks(client)

    response = await client.get(
        '/v2/usage/networks',
        params={
            'time_range': 'daily',
            'app_id': app.id,
            'gateway_id': ethereum.id,
            'chain': 'ethereum',
            'network': 'mainnet',
            'limit': 1,
        },
    )

    data = assert_ok_response(response)['data']
    assert [(item['chain'], item['network']) for item in data['items']] == [('ethereum', 'mainnet')]
    assert point_total(data['items'][0]) == 3


@pytest.mark.anyio
async def test_networks_require_authentication(client: AsyncClient) -> None:
    response = await client.get('/v2/usage/networks')

    assert response.status_code == 401, response.text
