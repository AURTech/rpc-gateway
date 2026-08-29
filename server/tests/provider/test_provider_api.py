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


@pytest.mark.anyio
async def test_provider_creation_limit_excludes_deleted_providers(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')
    payload = {
        'vendor': 'alchemy',
        'credential': {'secret': 'provider-secret'},
    }

    provider_ids: list[str] = []
    for index in range(6):
        response = await client.post('/v2/providers', json={**payload, 'name': f'Provider {index}'})
        assert response.status_code == 201, response.text
        provider_ids.append(response.json()['data']['id'])

    response = await client.post('/v2/providers', json={**payload, 'name': 'Provider over limit'})
    assert response.status_code == 400, response.text
    assert response.json()['msg'] == 'An account can have at most 6 providers.'

    response = await client.delete(f'/v2/providers/{provider_ids[0]}')
    assert response.status_code == 200, response.text

    response = await client.post('/v2/providers', json={**payload, 'name': 'Replacement provider'})
    assert response.status_code == 201, response.text
