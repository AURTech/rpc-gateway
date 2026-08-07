from datetime import UTC, datetime

import pytest
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointProtocol
from app.model.provider import ProviderVendor
from app.orm.account import Account
from app.orm.application import App
from app.orm.endpoint import Endpoint
from app.orm.provider import Provider
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


async def _seed_fleet(account_id: str) -> None:
    await App.create(account_id=account_id, name='Live app one')
    await App.create(account_id=account_id, name='Live app two')
    await App.create(account_id=account_id, name='Deleted app', deleted_at=datetime.now(UTC))

    await Endpoint.create(
        account_id=account_id,
        name='e-enabled',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url='encrypted-url',
    )
    await Endpoint.create(
        account_id=account_id,
        name='e-disabled',
        chain=Chain.POLYGON,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url='encrypted-url',
        enabled=False,
    )
    await Endpoint.create(
        account_id=account_id,
        name='e-enabled-2',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url='encrypted-url',
    )
    await Endpoint.create(
        account_id=account_id,
        name='e-deleted',
        chain=Chain.POLYGON,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url='encrypted-url',
        deleted_at=datetime.now(UTC),
    )

    await Provider.create(account_id=account_id, name='p-live-one', vendor=ProviderVendor.ALCHEMY, encrypted_credential='x')
    await Provider.create(account_id=account_id, name='p-live-two', vendor=ProviderVendor.QUICKNODE, encrypted_credential='x')
    await Provider.create(
        account_id=account_id,
        name='p-deleted',
        vendor=ProviderVendor.DRPC,
        encrypted_credential='x',
        deleted_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_overview_returns_fleet_totals(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')
    account = await Account.get(email='admin@example.com')
    await _seed_fleet(account.id)

    # Another account's fleet must not leak into the totals.
    other = await Account.create(email='other@example.com')
    await App.create(account_id=other.id, name='Other app')
    await Endpoint.create(
        account_id=other.id,
        name='other-e',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url='encrypted-url',
    )
    await Provider.create(account_id=other.id, name='other-p', vendor=ProviderVendor.ALCHEMY, encrypted_credential='x')

    response = await client.get('/v2/overview')

    data = assert_ok_response(response)['data']
    assert data == {
        'endpoint_total': 3,
        'active_endpoint_total': 2,
        'provider_total': 2,
        'app_total': 2,
    }


@pytest.mark.anyio
async def test_overview_empty_account_returns_zeros(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')

    response = await client.get('/v2/overview')

    data = assert_ok_response(response)['data']
    assert data == {
        'endpoint_total': 0,
        'active_endpoint_total': 0,
        'provider_total': 0,
        'app_total': 0,
    }


@pytest.mark.anyio
async def test_overview_requires_authentication(client: AsyncClient) -> None:
    response = await client.get('/v2/overview')

    assert response.status_code == 401, response.text
