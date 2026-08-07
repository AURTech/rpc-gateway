import pytest
from app.orm.account import Account
from app.orm.provider import Provider
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


@pytest.mark.anyio
async def test_provider_name_can_be_reused_after_delete(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')
    account = await Account.get(email='member@example.com')
    payload = {
        'name': 'Primary provider',
        'vendor': 'alchemy',
        'credential': {'secret': 'provider-secret'},
    }

    created_response = await client.post('/v2/providers', json=payload)

    assert created_response.status_code == 201, created_response.text
    created = created_response.json()['data']

    duplicate_response = await client.post('/v2/providers', json=payload)

    assert duplicate_response.status_code == 400, duplicate_response.text
    assert duplicate_response.json()['msg'] == 'Provider name already exists.'

    deleted_response = await client.delete(f'/v2/providers/{created["id"]}')

    assert deleted_response.status_code == 200, deleted_response.text
    assert deleted_response.json()['data'] == {
        'id': created['id'],
        'version': 2,
        'deleted': True,
        'archived_endpoints': 0,
        'retained_endpoints': 0,
        'detached_endpoints': 0,
    }

    recreated_response = await client.post('/v2/providers', json=payload)

    assert recreated_response.status_code == 201, recreated_response.text
    recreated = recreated_response.json()['data']
    assert recreated['id'] != created['id']
    assert await Provider.filter(account_id=account.id, name=payload['name'], deleted_at=None).count() == 1
    assert await Provider.filter(account_id=account.id, name=payload['name'], deleted_at__isnull=False).count() == 1
