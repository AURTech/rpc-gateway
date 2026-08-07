from datetime import datetime, timedelta

import pytest
from app.model.auth import PersonalAccessTokenScope
from app.orm.application import AppAuditEvent
from app.orm.auth import PersonalAccessToken
from app.services.auth.token import hash_pat
from app.util import datetime as datetime_util
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


async def create_pat(
    client: AsyncClient,
    scopes: list[PersonalAccessTokenScope],
    *,
    name: str = 'Codex',
) -> tuple[str, str]:
    response = await client.post(
        '/v2/auth/personal-access-tokens',
        json={'name': name, 'scopes': [scope.value for scope in scopes]},
    )
    assert response.status_code == 201, response.text
    data = response.json()['data']
    return data['id'], data['token']


@pytest.mark.anyio
async def test_pat_secret_is_returned_once_and_stored_as_hmac(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    token_id, raw_token = await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ])

    row = await PersonalAccessToken.get(id=token_id)
    assert row.token_digest == hash_pat(raw_token)
    assert raw_token not in row.token_digest

    response = await client.get('/v2/auth/personal-access-tokens')
    assert response.status_code == 200, response.text
    item = response.json()['data']['items'][0]
    assert response.json()['data']['active'] == 1
    assert response.json()['data']['max_active'] == 20
    assert item['id'] == token_id
    assert item['token_prefix'] == raw_token[:14]
    assert 'token' not in item
    expires_at = datetime.fromisoformat(item['expires_at'])
    assert timedelta(days=89) < expires_at - datetime_util.now_utc() <= timedelta(days=90)

    response = await client.post(
        '/v2/auth/personal-access-tokens',
        json={
            'name': 'Too long',
            'scopes': ['overview:read'],
            'expires_at': (datetime_util.now_utc() + timedelta(days=366)).isoformat(),
        },
    )
    assert response.status_code == 400, response.text


@pytest.mark.anyio
async def test_pat_limits_active_tokens_and_released_capacity_can_be_reused(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    token_ids = []
    for index in range(20):
        token_id, _ = await create_pat(
            client,
            [PersonalAccessTokenScope.OVERVIEW_READ],
            name=f'Agent {index + 1}',
        )
        token_ids.append(token_id)

    response = await client.post(
        '/v2/auth/personal-access-tokens',
        json={'name': 'Over limit', 'scopes': ['overview:read']},
    )
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'personal_access_tokens.limit_reached'
    assert response.json()['details'] == {'active': 20, 'max_active': 20}

    response = await client.delete(f'/v2/auth/personal-access-tokens/{token_ids[0]}')
    assert response.status_code == 200, response.text
    await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ], name='Replacement after revoke')

    await PersonalAccessToken.filter(id=token_ids[1]).update(expires_at=datetime_util.now_utc() - timedelta(seconds=1))
    await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ], name='Replacement after expiry')


@pytest.mark.anyio
async def test_pat_scope_allows_mapped_route_and_rejects_missing_scope(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    _, raw_token = await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ])
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Authorization'] = f'Bearer {raw_token}'

    response = await client.get('/v2/overview')
    assert response.status_code == 200, response.text

    response = await client.get('/v2/apps')
    assert response.status_code == 403, response.text
    body = response.json()
    assert body['code'] == 'auth.insufficient_scope'
    assert body['details'] == {'required_scopes': ['apps:read']}
    assert body['trace_id']


@pytest.mark.anyio
async def test_pat_rejects_ambiguous_cookie_and_bearer_credentials(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    _, raw_token = await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ])
    client.headers['Authorization'] = f'Bearer {raw_token}'

    response = await client.get('/v2/overview')
    assert response.status_code == 403, response.text
    assert response.json()['code'] == 'auth.multiple_credentials'


@pytest.mark.anyio
async def test_pat_without_endpoint_secret_scope_receives_redacted_detail(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    _, raw_token = await create_pat(client, [PersonalAccessTokenScope.ENDPOINTS_WRITE])
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Authorization'] = f'Bearer {raw_token}'

    response = await client.post(
        '/v2/endpoints',
        json={
            'name': 'AI upstream',
            'chain': 'ethereum',
            'network': 'mainnet',
            'protocol': 'jsonrpc',
            'url': 'https://rpc.example.com',
            'auth': {'type': 'bearer', 'secret': 'upstream-secret'},
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()['data']
    assert data['auth'] == {'type': 'bearer', 'has_secret': True}
    assert 'configured_url' not in data
    assert 'upstream-secret' not in response.text


@pytest.mark.anyio
async def test_user_cannot_create_admin_pat_and_disabled_account_invalidates_pat(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    response = await client.post('/v2/accounts', json={'email': 'member@example.com'})
    assert response.status_code == 201, response.text
    account_id = response.json()['data']['id']

    client.cookies.clear()
    await login_with_google(client, 'member@example.com', sub='member-sub')
    response = await client.post(
        '/v2/auth/personal-access-tokens',
        json={'name': 'Admin attempt', 'scopes': ['accounts:read']},
    )
    assert response.status_code == 403, response.text

    _, raw_token = await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ])
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    await login_with_google(client, 'admin@example.com')
    response = await client.post(f'/v2/accounts/{account_id}', json={'status': 'disabled'})
    assert response.status_code == 200, response.text

    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Authorization'] = f'Bearer {raw_token}'
    response = await client.get('/v2/overview')
    assert response.status_code == 401, response.text
    assert response.json()['code'] == 'auth.invalid_token'


@pytest.mark.anyio
async def test_revoked_and_expired_pat_are_rejected(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    token_id, raw_token = await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ])

    response = await client.delete(f'/v2/auth/personal-access-tokens/{token_id}')
    assert response.status_code == 200, response.text
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Authorization'] = f'Bearer {raw_token}'
    response = await client.get('/v2/overview')
    assert response.status_code == 401, response.text
    assert response.json()['code'] == 'auth.token_revoked'

    client.headers.pop('Authorization')
    await login_with_google(client, 'admin@example.com')
    second_id, second_token = await create_pat(client, [PersonalAccessTokenScope.OVERVIEW_READ], name='Expired')
    await PersonalAccessToken.filter(id=second_id).update(expires_at=datetime_util.now_utc() - timedelta(seconds=1))
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Authorization'] = f'Bearer {second_token}'
    response = await client.get('/v2/overview')
    assert response.status_code == 401, response.text
    assert response.json()['code'] == 'auth.token_expired'


@pytest.mark.anyio
async def test_pat_idempotency_replays_create_and_audits_token(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    token_id, raw_token = await create_pat(
        client,
        [PersonalAccessTokenScope.APPS_WRITE, PersonalAccessTokenScope.APP_KEYS_WRITE],
    )
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Authorization'] = f'Bearer {raw_token}'
    client.headers['Idempotency-Key'] = 'create-app-001'

    first = await client.post('/v2/apps', json={'name': 'AI managed app'})
    assert first.status_code == 201, first.text
    replay = await client.post('/v2/apps', json={'name': 'AI managed app'})
    assert replay.status_code == 201, replay.text
    assert replay.headers['Idempotency-Replayed'] == 'true'
    assert replay.headers['Cache-Control'] == 'private, no-store'
    assert replay.json() == first.json()

    assert await AppAuditEvent.filter(actor_token_id=token_id).count() == 2
    conflict = await client.post('/v2/apps', json={'name': 'Different app'})
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()['code'] == 'idempotency.conflict'


@pytest.mark.anyio
async def test_pat_idempotency_cache_is_isolated_between_pat_scopes(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com')
    response = await client.post(
        '/v2/providers',
        json={
            'name': 'Idempotency provider',
            'vendor': 'alchemy',
            'credential': {'secret': 'existing-provider-secret'},
        },
    )
    assert response.status_code == 201, response.text
    provider = response.json()['data']

    _, privileged_token = await create_pat(
        client,
        [PersonalAccessTokenScope.PROVIDERS_WRITE, PersonalAccessTokenScope.PROVIDER_SECRETS_READ],
        name='Privileged provider agent',
    )
    _, restricted_token = await create_pat(
        client,
        [PersonalAccessTokenScope.PROVIDERS_WRITE],
        name='Restricted provider agent',
    )
    client.cookies.clear()
    client.headers.pop('X-RPC-Gateway-CSRF', None)
    client.headers['Idempotency-Key'] = 'provider-scope-isolation'
    payload = {'expected_version': provider['version'], 'name': provider['name']}

    client.headers['Authorization'] = f'Bearer {privileged_token}'
    privileged = await client.patch(f'/v2/providers/{provider["id"]}', json=payload)
    assert privileged.status_code == 200, privileged.text
    assert privileged.json()['data']['credential'] == {
        'has_secret': True,
        'secret': 'existing-provider-secret',
    }

    client.headers['Authorization'] = f'Bearer {restricted_token}'
    restricted = await client.patch(f'/v2/providers/{provider["id"]}', json=payload)
    assert restricted.status_code == 200, restricted.text
    assert 'Idempotency-Replayed' not in restricted.headers
    assert restricted.json()['data']['credential'] == {'has_secret': True}

    restricted_replay = await client.patch(f'/v2/providers/{provider["id"]}', json=payload)
    assert restricted_replay.status_code == 200, restricted_replay.text
    assert restricted_replay.headers['Idempotency-Replayed'] == 'true'
    assert restricted_replay.json()['data']['credential'] == {'has_secret': True}
