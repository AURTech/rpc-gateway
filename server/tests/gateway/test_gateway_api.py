import pytest
from app.model.application import AppAuditAction
from app.orm.account import Account
from app.orm.application import App, AppAuditEvent
from app.orm.gateway import Gateway
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


async def create_gateway(app_id: str, *, name: str, network: str, enabled: bool = True) -> Gateway:
    return await Gateway.create(
        app_id=app_id,
        name=name,
        chain='ethereum',
        network=network,
        transport_types=['jsonrpc'],
        enabled=enabled,
        version=1,
    )


@pytest.mark.anyio
async def test_bulk_update_gateways_is_atomic_and_returns_request_order(client: AsyncClient) -> None:
    account = await Account.create(email='member@example.com')
    app = await App.create(account_id=account.id, name='Bulk app')
    mainnet = await create_gateway(app.id, name='mainnet', network='mainnet')
    sepolia = await create_gateway(app.id, name='sepolia', network='sepolia')
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.patch(
        f'/v2/apps/{app.id}/gateways',
        json={
            'enabled': False,
            'gateways': [
                {'id': sepolia.id, 'expected_version': sepolia.version},
                {'id': mainnet.id, 'expected_version': mainnet.version},
            ],
        },
    )

    data = assert_ok_response(response)['data']
    assert data['total'] == 2
    assert [item['id'] for item in data['items']] == [sepolia.id, mainnet.id]
    assert [(item['enabled'], item['effective_enabled'], item['version']) for item in data['items']] == [
        (False, False, 2),
        (False, False, 2),
    ]
    assert await Gateway.filter(id__in=[mainnet.id, sepolia.id], enabled=False, version=2).count() == 2
    audits = await AppAuditEvent.filter(resource_id__in=[mainnet.id, sepolia.id]).order_by('resource_id')
    assert len(audits) == 2
    assert all(audit.action == AppAuditAction.UPDATED for audit in audits)
    assert all(audit.previous_version == 1 and audit.new_version == 2 for audit in audits)
    assert all(audit.changed_fields == ['enabled'] for audit in audits)


@pytest.mark.anyio
async def test_bulk_update_gateways_keeps_noop_version_and_audit(client: AsyncClient) -> None:
    account = await Account.create(email='member@example.com')
    app = await App.create(account_id=account.id, name='Bulk app')
    gateway = await create_gateway(app.id, name='mainnet', network='mainnet', enabled=False)
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.patch(
        f'/v2/apps/{app.id}/gateways',
        json={'enabled': False, 'gateways': [{'id': gateway.id, 'expected_version': gateway.version}]},
    )

    item = assert_ok_response(response)['data']['items'][0]
    assert item['enabled'] is False
    assert item['version'] == 1
    assert await AppAuditEvent.filter(resource_id=gateway.id).count() == 0


@pytest.mark.anyio
async def test_bulk_update_gateways_rolls_back_on_version_conflict(client: AsyncClient) -> None:
    account = await Account.create(email='member@example.com')
    app = await App.create(account_id=account.id, name='Bulk app')
    mainnet = await create_gateway(app.id, name='mainnet', network='mainnet')
    sepolia = await create_gateway(app.id, name='sepolia', network='sepolia')
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.patch(
        f'/v2/apps/{app.id}/gateways',
        json={
            'enabled': False,
            'gateways': [
                {'id': mainnet.id, 'expected_version': 1},
                {'id': sepolia.id, 'expected_version': 2},
            ],
        },
    )

    assert response.status_code == 400, response.text
    assert response.json()['msg'] == 'Gateway version conflict. Reload the Gateways before saving.'
    assert await Gateway.filter(id__in=[mainnet.id, sepolia.id], enabled=True, version=1).count() == 2
    assert await AppAuditEvent.filter(resource_id__in=[mainnet.id, sepolia.id]).count() == 0


@pytest.mark.anyio
async def test_bulk_update_gateways_rolls_back_for_another_account(client: AsyncClient) -> None:
    account = await Account.create(email='member@example.com')
    app = await App.create(account_id=account.id, name='Bulk app')
    owned = await create_gateway(app.id, name='mainnet', network='mainnet')
    other = await Account.create(email='other@example.com')
    other_app = await App.create(account_id=other.id, name='Other app')
    foreign = await create_gateway(other_app.id, name='sepolia', network='sepolia')
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.patch(
        f'/v2/apps/{app.id}/gateways',
        json={
            'enabled': False,
            'gateways': [
                {'id': owned.id, 'expected_version': 1},
                {'id': foreign.id, 'expected_version': 1},
            ],
        },
    )

    assert response.status_code == 404, response.text
    assert await Gateway.filter(id=owned.id, enabled=True, version=1).exists()
    assert await AppAuditEvent.filter(resource_id=owned.id).count() == 0

    response = await client.patch(
        f'/v2/apps/{other_app.id}/gateways',
        json={'enabled': False, 'gateways': [{'id': foreign.id, 'expected_version': 1}]},
    )

    assert response.status_code == 404, response.text
    assert response.json()['msg'] == 'App not found.'
    assert await Gateway.filter(id=foreign.id, enabled=True, version=1).exists()
