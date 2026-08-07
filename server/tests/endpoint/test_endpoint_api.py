import pytest
from app.orm.account import Account
from app.orm.application import App
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteTarget
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


async def create_endpoint(account_id: str, name: str) -> Endpoint:
    return await Endpoint.create(
        account_id=account_id,
        name=name,
        chain='ethereum',
        network='mainnet',
        protocol='jsonrpc',
        encrypted_url='encrypted-url',
        enabled=True,
        auth_type='none',
        version=1,
    )


@pytest.mark.anyio
async def test_bulk_delete_endpoint_api_returns_deleted_and_referenced_targets(client: AsyncClient) -> None:
    account = await Account.create(email='member@example.com')
    deletable = await create_endpoint(account.id, 'deletable')
    referenced = await create_endpoint(account.id, 'referenced')
    app = await App.create(account_id=account.id, name='Bulk app')
    gateway = await Gateway.create(
        app_id=app.id,
        name='ethereum-mainnet',
        chain='ethereum',
        network='mainnet',
        transport_types=['jsonrpc'],
    )
    route = await JsonRpcRoute.create(gateway_id=gateway.id)
    await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=referenced.id, position=0, weight=100)
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.post(
        '/v2/endpoints/bulk-delete',
        json={'endpoint_ids': [deletable.id, referenced.id]},
    )

    data = assert_ok_response(response)['data']
    assert data['total'] == 2
    assert [item['id'] for item in data['deleted']] == [deletable.id]
    assert data['referenced_ids'] == [referenced.id]
