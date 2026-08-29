from datetime import UTC, datetime
from typing import TypedDict

import pytest
from app.model.account import AccountBase, AccountDetail, AccountRole, CreateAccountParams, UpdateAccountStatusParams
from app.orm.account.account import Account, AccountStatus
from app.orm.application import App
from app.orm.auth import Auth, AuthProvider, AuthSession
from app.orm.gateway import Gateway
from app.services.account import account as account_service
from httpx import AsyncClient
from tests.auth.fixtures import login_with_google
from tests.helpers import assert_ok_response

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


class LogRecord(TypedDict):
    level: str
    message: str


class CapturingLog:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []

    def info(self, message: str) -> None:
        self.records.append({'level': 'info', 'message': message})

    def warning(self, message: str) -> None:
        self.records.append({'level': 'warning', 'message': message})


def assert_log_has_no_email(log: CapturingLog) -> None:
    assert 'example.com' not in repr(log.records)


USER_DETAIL_ONLY_FIELDS = {
    'first_login_at',
    'last_login_at',
    'last_login_ip',
    'last_login_user_agent',
    'gateway_count',
    'app_count',
}


@pytest.fixture
def account_log(monkeypatch: pytest.MonkeyPatch) -> CapturingLog:
    log = CapturingLog()
    monkeypatch.setattr(account_service, 'log', log)
    return log


@pytest.mark.anyio
async def test_admin_can_create_and_manage_accounts(client: AsyncClient, account_log: CapturingLog) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')

    response = await client.post('/v2/accounts', json={'email': 'New.Account@Example.COM'})
    assert response.status_code == 201, response.text
    data = response.json()['data']
    assert data['email'] == 'new.account@example.com'
    assert data['role'] == 'user'
    assert data['role_label'] == 'User'
    assert data['status'] == 'active'
    assert data['status_label'] == 'Active'
    assert data['activated'] is False
    account_id = data['id']
    await Account.filter(id=account_id).update(
        first_login_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_login_at=datetime(2024, 1, 2, tzinfo=UTC),
        last_login_ip='203.0.113.10',
        last_login_user_agent='pytest-agent',
    )

    response = await client.get('/v2/accounts')
    data = assert_ok_response(response)
    assert data['data']['page'] == 1
    assert data['data']['size'] == 10
    assert data['data']['total'] == 1
    assert data['data']['max_page'] == 1
    assert data['data']['items'][0]['email'] == 'new.account@example.com'
    assert data['data']['items'][0]['activated'] is True
    assert USER_DETAIL_ONLY_FIELDS.isdisjoint(data['data']['items'][0])

    response = await client.get(f'/v2/accounts/{account_id}')
    detail = assert_ok_response(response)['data']
    for field in USER_DETAIL_ONLY_FIELDS:
        assert field in detail
    assert detail['first_login_at'] is not None
    assert detail['last_login_at'] is not None
    assert detail['last_login_ip'] == '203.0.113.10'
    assert detail['last_login_user_agent'] == 'pytest-agent'
    assert detail['gateway_count'] == 0
    assert detail['app_count'] == 0

    response = await client.post(f'/v2/accounts/{account_id}', json={'status': 'disabled'})
    data = assert_ok_response(response)['data']
    assert data['status'] == 'disabled'
    assert data['status_label'] == 'Disabled'
    obj = await Account.get(id=account_id)
    assert obj.status == AccountStatus.DISABLED

    response = await client.post(f'/v2/accounts/{account_id}', json={'status': 'active'})
    data = assert_ok_response(response)['data']
    assert data['status'] == 'active'
    assert data['status_label'] == 'Active'
    obj = await Account.get(id=account_id)
    assert obj.status == AccountStatus.ACTIVE

    response = await client.post('/v2/accounts/delete', json={'ids': [account_id]})
    assert_ok_response(response)
    obj = await Account.get(id=account_id)
    assert obj.status == AccountStatus.ARCHIVED

    response = await client.get('/v2/accounts', params={'page': 2, 'size': 10})
    data = assert_ok_response(response)
    assert data['data'] == {'page': 2, 'size': 10, 'total': 0, 'max_page': 0, 'items': []}

    assert account_log.records[0]['message'].startswith('Account ')
    assert ' created | Actor:' in account_log.records[0]['message']
    assert 'Status:active->disabled' in account_log.records[1]['message']
    assert 'RevokedSessions:0' in account_log.records[1]['message']
    assert account_log.records[2]['message'].startswith('Account status updated | ')
    assert account_log.records[3]['message'].startswith('Account ')
    assert ' archived | Actor:' in account_log.records[3]['message']
    assert 'RevokedSessions:0' in account_log.records[3]['message']
    assert_log_has_no_email(account_log)


@pytest.mark.anyio
async def test_duplicate_user_create_logs_without_email(client: AsyncClient, account_log: CapturingLog) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')
    await client.post('/v2/accounts', json={'email': 'New.Account@Example.COM'})

    response = await client.post('/v2/accounts', json={'email': 'New.Account@Example.COM'})

    assert response.status_code == 400
    assert account_log.records[-1]['level'] == 'warning'
    assert account_log.records[-1]['message'].startswith('Email already exists | ')
    assert 'Actor:' in account_log.records[-1]['message']
    assert_log_has_no_email(account_log)


def test_account_user_params_reject_invalid_values() -> None:
    invalid_emails = [
        'member example@example.com',
        'member@@example.com',
        'member@example',
    ]
    for email in invalid_emails:
        with pytest.raises(ValueError, match='Invalid email\\.'):
            CreateAccountParams(email=email)

    with pytest.raises(ValueError, match='Account status can only be active or disabled\\.'):
        UpdateAccountStatusParams(status=AccountStatus.ARCHIVED)


def test_account_base_and_detail_fields_are_split() -> None:
    assert USER_DETAIL_ONLY_FIELDS.isdisjoint(AccountBase.model_fields)
    assert USER_DETAIL_ONLY_FIELDS.issubset(AccountDetail.model_fields)


@pytest.mark.anyio
async def test_archived_user_releases_email_and_google_auth(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')
    response = await client.post('/v2/accounts', json={'email': 'member@example.com'})
    account_id = response.json()['data']['id']

    user_cookie = await login_with_google(client, 'member@example.com', sub='member-sub')
    client.cookies.set('rpc_gateway_session', user_cookie)
    response = await client.get('/v2/auth/me')
    assert response.status_code == 200

    client.cookies.clear()
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')
    response = await client.post('/v2/accounts/delete', json={'ids': [account_id]})
    archived = assert_ok_response(response)['data']['items'][0]
    assert archived['email'] == 'member@example.com'

    stored = await Account.get(id=account_id)
    assert stored.email == f'archived+{account_id}@deleted.local'
    archived_auth = await Auth.get(account_id=account_id, provider=AuthProvider.GOOGLE, deleted_at__isnull=False)
    assert archived_auth.identifier == f'archived+{archived_auth.id}'
    assert await AuthSession.filter(account_id=account_id, revoked_at__isnull=False).count() == 1

    client.cookies.clear()
    client.cookies.set('rpc_gateway_session', user_cookie)
    response = await client.get('/v2/auth/me')
    assert response.status_code == 401

    client.cookies.clear()
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')
    response = await client.post('/v2/accounts', json={'email': 'member@example.com'})
    assert response.status_code == 201, response.text
    new_account_id = response.json()['data']['id']

    client.cookies.clear()
    await login_with_google(client, 'member@example.com', sub='member-sub')
    assert await Auth.filter(account_id=new_account_id, provider=AuthProvider.GOOGLE, identifier='member-sub').count() == 1


@pytest.mark.anyio
async def test_admin_can_archive_multiple_accounts(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub', name='Admin Account')
    first_response = await client.post('/v2/accounts', json={'email': 'first@example.com'})
    second_response = await client.post('/v2/accounts', json={'email': 'second@example.com'})
    first_id = first_response.json()['data']['id']
    second_id = second_response.json()['data']['id']

    response = await client.post('/v2/accounts/delete', json={'ids': [first_id, second_id]})

    data = assert_ok_response(response)['data']
    assert data['total'] == 2
    assert [item['id'] for item in data['items']] == [first_id, second_id]
    assert await Account.filter(id__in=[first_id, second_id], status=AccountStatus.ARCHIVED).count() == 2


@pytest.mark.anyio
async def test_account_detail_counts_apps(client: AsyncClient) -> None:
    account = await Account.create(email='member@example.com')
    app = await App.create(account_id=account.id, name='prod-server', enabled=True, version=1)
    await Gateway.create(
        app_id=app.id,
        name='mainnet',
        chain='ethereum',
        network='mainnet',
        transport_types=['jsonrpc'],
        enabled=True,
        version=1,
    )

    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    response = await client.get(f'/v2/accounts/{account.id}')
    detail = assert_ok_response(response)['data']
    assert detail['gateway_count'] == 1
    assert detail['app_count'] == 1

    await App.filter(id=app.id).update(deleted_at=datetime.now(UTC))

    client.cookies.clear()
    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    response = await client.get(f'/v2/accounts/{account.id}')
    detail = assert_ok_response(response)['data']
    assert detail['gateway_count'] == 0
    assert detail['app_count'] == 0


@pytest.mark.anyio
async def test_list_accounts_excludes_soft_deleted_rows(client: AsyncClient) -> None:
    account = await Account.create(email='deleted@example.com', status=AccountStatus.ACTIVE, deleted_at=datetime.now(UTC))

    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    response = await client.get('/v2/accounts')
    data = assert_ok_response(response)['data']

    assert data['total'] == 0
    assert data['items'] == []
    assert await Account.filter(id=account.id).exists()


@pytest.mark.anyio
async def test_list_accounts_excludes_admin_accounts(client: AsyncClient) -> None:
    await Account.create(email='platform-admin@example.com', role=AccountRole.ADMIN, status=AccountStatus.ACTIVE)

    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    response = await client.get('/v2/accounts')
    data = assert_ok_response(response)['data']

    assert data['total'] == 0
    assert data['items'] == []


@pytest.mark.anyio
async def test_list_accounts_filters_time_range_and_sorts_created_at(client: AsyncClient) -> None:
    first = await Account.create(email='first@example.com')
    second = await Account.create(email='second@example.com')
    third = await Account.create(email='third@example.com')
    await Account.filter(id=first.id).update(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    await Account.filter(id=second.id).update(created_at=datetime(2026, 2, 1, tzinfo=UTC))
    await Account.filter(id=third.id).update(created_at=datetime(2026, 3, 1, tzinfo=UTC))
    await login_with_google(client, 'admin@example.com', sub='admin-sub')

    response = await client.get('/v2/accounts')
    data = assert_ok_response(response)['data']
    assert [item['email'] for item in data['items']] == ['third@example.com', 'second@example.com', 'first@example.com']

    response = await client.get('/v2/accounts', params={'sort': 'ASC'})
    data = assert_ok_response(response)['data']
    assert [item['email'] for item in data['items']] == ['first@example.com', 'second@example.com', 'third@example.com']

    response = await client.get(
        '/v2/accounts',
        params={'start_at': '2026-02-01T00:00:00Z', 'end_at': '2026-03-01T00:00:00Z'},
    )
    data = assert_ok_response(response)['data']
    assert data['total'] == 1
    assert data['items'][0]['email'] == 'second@example.com'


@pytest.mark.anyio
async def test_disabled_user_session_is_invalidated(client: AsyncClient, account_log: CapturingLog) -> None:
    account = await Account.create(email='member@example.com')
    user_cookie = await login_with_google(client, 'member@example.com', sub='member-sub')
    assert await AuthSession.filter(account_id=account.id, revoked_at__isnull=True).count() == 1

    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    response = await client.post(f'/v2/accounts/{account.id}', json={'status': 'disabled'})
    assert_ok_response(response)

    client.cookies.clear()
    client.cookies.set('rpc_gateway_session', user_cookie)
    response = await client.get('/v2/auth/me')
    assert response.status_code == 401
    assert await AuthSession.filter(account_id=account.id, revoked_at__isnull=False).count() == 1

    status_log = account_log.records[-1]
    assert status_log['message'].startswith('Account status updated | ')
    assert f'Account:{account.id}' in status_log['message']
    assert 'Status:active->disabled' in status_log['message']
    assert 'RevokedSessions:1' in status_log['message']
    assert_log_has_no_email(account_log)
