import asyncio
from typing import NotRequired, TypedDict
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.api.v2.auth.auth import _frontend_callback_url
from app.api.v2.auth.cookie import set_session_cookie
from app.clients.auth import AurPayProfile
from app.core.config import Config
from app.model.account import AccountRole, AccountStatus, ArchiveAccountsParams, UpdateAccountStatusParams
from app.orm.account.account import Account
from app.orm.auth import Auth, AuthProvider, AuthSession
from app.services.account import AccountManager
from app.services.auth import auth as auth_service
from app.services.auth.csrf import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.services.auth.password import hash_password
from app.services.auth.session import (
    OAUTH_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    IssuedSession,
    build_oauth_login_state,
    parse_oauth_state_cookie,
)
from app.services.auth.settings import get_auth_settings
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.requests import Request
from starlette.responses import Response
from tests.auth.fixtures import login_with_google, start_google_login
from tests.helpers import asgi_client, assert_ok_response
from tortoise.backends.base.client import BaseDBAsyncClient

pytestmark = pytest.mark.usefixtures('auth_env', 'fake_google')


class LogRecord(TypedDict):
    level: str
    message: str
    extra: NotRequired[dict[str, object]]


class BoundCapturingLog:
    def __init__(self, records: list[LogRecord], extra: dict[str, object]) -> None:
        self._records = records
        self._extra = extra

    def info(self, message: str) -> None:
        self._records.append({'level': 'info', 'message': message, 'extra': self._extra})


class CapturingLog:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []

    def info(self, message: str) -> None:
        self.records.append({'level': 'info', 'message': message})

    def warning(self, message: str) -> None:
        self.records.append({'level': 'warning', 'message': message})

    def bind(self, **extra: object) -> BoundCapturingLog:
        return BoundCapturingLog(self.records, extra)


def assert_log_has_no_sensitive_auth_values(log: CapturingLog) -> None:
    payload = repr(log.records)
    assert 'example.com' not in payload
    assert 'code:' not in payload
    assert 'rpc_gateway_session' not in payload


def build_auth_request(headers: dict[str, str], client_host: str) -> Request:
    return Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': '/v2/auth/google/login',
            'headers': [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            'client': (client_host, 12345),
            'server': ('testserver', 80),
            'scheme': 'http',
            'query_string': b'',
        }
    )


def set_cookie_headers(response: Response) -> list[str]:
    return [value.decode().lower() for key, value in response.raw_headers if key == b'set-cookie']


@pytest.fixture
def auth_log(monkeypatch: pytest.MonkeyPatch) -> CapturingLog:
    log = CapturingLog()
    monkeypatch.setattr(auth_service, 'log', log)
    return log


def test_auth_settings_reads_values_from_config_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        'ADMIN_ALLOWED_EMAILS',
        'AUTH_COOKIE_SAMESITE',
        'AUTH_COOKIE_SECURE',
        'AUTH_PAT_HASH_SECRET',
        'AUTH_SESSION_SECRET',
        'CORS_ORIGINS',
        'ENDPOINT_KEYRING',
        'FRONTEND_AUTH_CALLBACK_URL',
        'GOOGLE_OAUTH_CLIENT_ID',
        'GOOGLE_OAUTH_CLIENT_SECRET',
        'GOOGLE_OAUTH_REDIRECT_URI',
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / '.env.auth'
    env_file.write_text(
        '\n'.join(
            [
                'APP_ENV=prod',
                'GOOGLE_OAUTH_CLIENT_ID=env-client',
                'GOOGLE_OAUTH_CLIENT_SECRET=env-secret',
                'GOOGLE_OAUTH_REDIRECT_URI=https://dash.example.com/v2/auth/google/callback',
                'FRONTEND_AUTH_CALLBACK_URL=https://dash.example.com/zh/auth/callback',
                'CORS_ORIGINS=["https://dash.example.com"]',
                'ADMIN_ALLOWED_EMAILS=["Admin@Example.com","other@example.com"]',
                'AUTH_SESSION_SECRET=env-session-secret-value-32-bytes',
                'AUTH_PAT_HASH_SECRET=env-pat-hash-secret-value-32-bytes',
                'AUTH_COOKIE_SAMESITE=lax',
                'AUTH_COOKIE_SECURE=true',
                'ENDPOINT_KEYRING={"v1":"test-endpoint-encryption-key-32-bytes"}',
            ]
        )
    )

    settings = get_auth_settings(Config(**{'_env_file': env_file}))

    assert settings.google_client_id == 'env-client'
    assert settings.google_client_secret == 'env-secret'
    assert settings.google_redirect_uri == 'https://dash.example.com/v2/auth/google/callback'
    assert settings.frontend_auth_callback_url == 'https://dash.example.com/zh/auth/callback'
    assert settings.admin_allowed_emails == frozenset({'admin@example.com', 'other@example.com'})
    assert settings.session_secret == 'env-session-secret-value-32-bytes'
    assert settings.cookie_samesite == 'lax'
    assert settings.cookie_secure is True


def test_auth_session_cookie_uses_configured_cross_site_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Response()
    conf = Config.model_validate(
        {
            'APP_ENV': 'dev',
            'AUTH_COOKIE_SAMESITE': 'lax',
            'AUTH_COOKIE_SECURE': True,
        }
    )
    monkeypatch.setattr('app.services.auth.settings.get_conf', lambda: conf)

    set_session_cookie(response, 'user.token')

    cookies = set_cookie_headers(response)
    assert any('samesite=lax' in cookie and 'secure' in cookie for cookie in cookies)
    assert all('domain=' not in cookie for cookie in cookies)


def test_oauth_state_cookie_preserves_frontend_callback_url() -> None:
    callback_url = 'http://127.0.0.1:19341/zh/auth/callback'

    login_state = build_oauth_login_state(callback_url)
    parsed = parse_oauth_state_cookie(login_state.state, login_state.cookie_value)

    assert parsed is not None
    assert parsed.code_verifier == login_state.code_verifier
    assert parsed.frontend_callback_url == callback_url


def test_oauth_state_cookie_rejects_malformed_callback_url() -> None:
    login_state = build_oauth_login_state('http://127.0.0.1:19341/zh/auth/callback')
    parts = login_state.cookie_value.split('.')
    parts[2] = '!!!!'

    assert parse_oauth_state_cookie(login_state.state, '.'.join(parts)) is None


def test_google_login_uses_allowed_referer_callback_url(auth_env: dict[str, object]) -> None:
    auth_env['CORS_ORIGINS'] = ['http://127.0.0.1:19341', 'https://console-entry.test']
    request = build_auth_request(
        {
            'host': 'gateway-entry.test',
            'referer': 'http://127.0.0.1:19341/zh/login',
        },
        client_host='203.0.113.10',
    )

    assert _frontend_callback_url(request) == 'http://127.0.0.1:19341/zh/auth/callback'


def test_google_login_rejects_unlisted_referer_callback_url(auth_env: dict[str, object]) -> None:
    auth_env['CORS_ORIGINS'] = ['http://127.0.0.1:19341', 'https://console-entry.test']
    request = build_auth_request(
        {
            'host': 'gateway-entry.test',
            'referer': 'https://evil.example/zh/login',
        },
        client_host='203.0.113.10',
    )

    assert _frontend_callback_url(request) == 'http://web.test/zh/auth/callback'


async def _create_password_user(
    email: str,
    password: str,
    *,
    role: AccountRole = AccountRole.USER,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> Account:
    return await Account.create(
        email=email,
        role=role,
        status=status,
        password_hash=hash_password(password),
    )


@pytest.mark.anyio
async def test_password_login_issues_user_session(client: AsyncClient) -> None:
    await _create_password_user('member@example.com', 'member-pass-123')

    response = await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'member-pass-123'})

    data = assert_ok_response(response)['data']
    assert data['identity_type'] == 'user'
    assert data['email'] == 'member@example.com'
    assert response.cookies.get(SESSION_COOKIE_NAME)
    assert 'httponly' in response.headers['set-cookie'].lower()

    me = assert_ok_response(await client.get('/v2/auth/me'))['data']
    assert me['identity_type'] == 'user'
    assert me['email'] == 'member@example.com'


@pytest.mark.anyio
async def test_first_password_login_marks_new_user_message_for_grafana(
    client: AsyncClient,
    auth_log: CapturingLog,
) -> None:
    account = await _create_password_user('member@example.com', 'member-pass-123')

    first = await client.post('/v2/auth/login', json={'email': account.email, 'password': 'member-pass-123'})
    second = await client.post('/v2/auth/login', json={'email': account.email, 'password': 'member-pass-123'})

    assert first.status_code == 200
    assert second.status_code == 200
    await account.refresh_from_db()
    assert account.first_login_at is not None
    notifications = [record for record in auth_log.records if record.get('extra') == {'send_msg': True}]
    assert notifications == [
        {
            'level': 'info',
            'message': f'New user | Account:{account.id} | Login:Password',
            'extra': {'send_msg': True},
        }
    ]
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_new_aurpay_registration_marks_new_user_message_for_grafana(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    auth_log: CapturingLog,
) -> None:
    _ = client

    async def fetch_profile(*_args: object, **_kwargs: object) -> AurPayProfile:
        return AurPayProfile(sub='aurpay-sub', email='member@example.com', name='Member Account')

    monkeypatch.setattr(auth_service, 'fetch_aurpay_profile', fetch_profile)
    first = await app.state.auth_manager.login_with_aurpay(
        'code',
        'verifier',
        'nonce',
        client_ip='203.0.113.10',
        user_agent='pytest',
    )
    await app.state.auth_manager.login_with_aurpay(
        'code',
        'verifier',
        'nonce',
        client_ip='203.0.113.10',
        user_agent='pytest',
    )

    account = await Account.get(id=first.result.id)
    notifications = [record for record in auth_log.records if record.get('extra') == {'send_msg': True}]
    assert notifications == [
        {
            'level': 'info',
            'message': f'New user | Account:{account.id} | Login:AurPay',
            'extra': {'send_msg': True},
        }
    ]
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_password_login_issues_admin_session(client: AsyncClient) -> None:
    await _create_password_user('admin@example.com', 'admin-pass-123', role=AccountRole.ADMIN)

    response = await client.post('/v2/auth/login', json={'email': 'admin@example.com', 'password': 'admin-pass-123'})

    data = assert_ok_response(response)['data']
    assert data['identity_type'] == 'admin'

    me = assert_ok_response(await client.get('/v2/auth/me'))['data']
    assert me['identity_type'] == 'admin'
    assert me['email'] == 'admin@example.com'


@pytest.mark.anyio
async def test_password_login_rejects_wrong_password(client: AsyncClient) -> None:
    await _create_password_user('member@example.com', 'member-pass-123')

    response = await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'wrong-password'})

    assert response.status_code == 401
    assert response.json()['msg'] == 'Invalid email or password.'
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


@pytest.mark.anyio
async def test_password_login_rejects_account_without_password(client: AsyncClient) -> None:
    await Account.create(email='member@example.com', status=AccountStatus.ACTIVE)

    response = await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'any-password-123'})

    assert response.status_code == 401
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


@pytest.mark.anyio
async def test_password_login_runs_dummy_verification_for_missing_password_hashes(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_hashes: list[str | None] = []

    async def fake_verify(raw: str, stored: str | None) -> bool:
        assert raw == 'candidate-password'
        verified_hashes.append(stored)
        return False

    monkeypatch.setattr(app.state.auth_manager._password_worker, 'verify', fake_verify)
    await Account.create(email='without-password@example.com', status=AccountStatus.ACTIVE)

    missing = await client.post(
        '/v2/auth/login',
        json={'email': 'missing@example.com', 'password': 'candidate-password'},
    )
    unset = await client.post(
        '/v2/auth/login',
        json={'email': 'without-password@example.com', 'password': 'candidate-password'},
    )

    assert missing.status_code == 401
    assert unset.status_code == 401
    assert verified_hashes == [None, None]


@pytest.mark.anyio
async def test_password_login_is_rate_limited_per_normalized_identity(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_password(raw: str, stored: str | None) -> bool:
        _ = raw
        _ = stored
        return False

    monkeypatch.setattr(app.state.auth_manager._password_worker, 'verify', reject_password)

    for index in range(5):
        email = 'Missing@Example.com' if index % 2 else 'missing@example.com'
        response = await client.post('/v2/auth/login', json={'email': email, 'password': 'candidate-password'})
        assert response.status_code == 401

    limited = await client.post(
        '/v2/auth/login',
        json={'email': 'missing@example.com', 'password': 'candidate-password'},
    )
    other_identity = await client.post(
        '/v2/auth/login',
        json={'email': 'other@example.com', 'password': 'candidate-password'},
    )
    assert limited.status_code == 429
    assert other_identity.status_code == 401


@pytest.mark.anyio
async def test_password_login_rejects_disabled_user(client: AsyncClient) -> None:
    await _create_password_user('member@example.com', 'member-pass-123', status=AccountStatus.DISABLED)

    response = await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'member-pass-123'})

    assert response.status_code == 403
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


@pytest.mark.anyio
async def test_disable_waits_for_password_session_and_revokes_it(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await _create_password_user('member@example.com', 'member-pass-123')
    session_entered = asyncio.Event()
    release_session = asyncio.Event()
    issue_session = auth_service.issue_user_session

    async def issue_after_barrier(
        account_id: str,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> IssuedSession:
        session_entered.set()
        await release_session.wait()
        return await issue_session(account_id, using_db=using_db)

    monkeypatch.setattr(auth_service, 'issue_user_session', issue_after_barrier)
    login_task = asyncio.create_task(
        client.post('/v2/auth/login', json={'email': account.email, 'password': 'member-pass-123'})
    )
    await session_entered.wait()

    disable_started = asyncio.Event()

    async def disable_account() -> None:
        disable_started.set()
        await AccountManager.update_account_status(
            account.id,
            UpdateAccountStatusParams(status=AccountStatus.DISABLED),
        )

    disable_task = asyncio.create_task(disable_account())
    await disable_started.wait()
    done, _pending = await asyncio.wait({disable_task}, timeout=0.1)
    disable_blocked = not done
    release_session.set()
    login_response, _ = await asyncio.gather(login_task, disable_task)

    assert disable_blocked
    assert login_response.status_code == 200
    await account.refresh_from_db()
    assert account.status == AccountStatus.DISABLED
    assert await AuthSession.filter(account_id=account.id, revoked_at=None).count() == 0


@pytest.mark.anyio
async def test_password_login_rejects_changed_hash_snapshot(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await _create_password_user('member@example.com', 'old-pass-123')
    verify_entered = asyncio.Event()
    release_verify = asyncio.Event()

    async def verify_after_barrier(raw: str, stored: str | None) -> bool:
        _ = raw
        _ = stored
        verify_entered.set()
        await release_verify.wait()
        return True

    monkeypatch.setattr(app.state.auth_manager, '_verify_password', verify_after_barrier)
    login_task = asyncio.create_task(client.post('/v2/auth/login', json={'email': account.email, 'password': 'old-pass-123'}))
    await verify_entered.wait()
    replacement_hash = hash_password('new-pass-123')
    await Account.filter(id=account.id).update(password_hash=replacement_hash)
    release_verify.set()

    response = await login_task

    assert response.status_code == 401
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    assert await AuthSession.filter(account_id=account.id).count() == 0
    await account.refresh_from_db()
    assert account.password_hash == replacement_hash


@pytest.mark.anyio
@pytest.mark.parametrize('account_status', [AccountStatus.DISABLED, AccountStatus.ARCHIVED])
async def test_password_login_does_not_reactivate_inactive_admin(
    client: AsyncClient,
    account_status: AccountStatus,
) -> None:
    admin = await _create_password_user(
        'admin@example.com',
        'admin-pass-123',
        role=AccountRole.ADMIN,
        status=account_status,
    )

    response = await client.post('/v2/auth/login', json={'email': admin.email, 'password': 'admin-pass-123'})

    assert response.status_code == 403
    await admin.refresh_from_db()
    assert admin.role == AccountRole.ADMIN
    assert admin.status == account_status


@pytest.mark.anyio
async def test_allowlisted_user_disable_wins_password_login(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await _create_password_user('admin@example.com', 'admin-pass-123')
    verify_entered = asyncio.Event()
    release_verify = asyncio.Event()

    async def verify_after_barrier(raw: str, stored: str | None) -> bool:
        _ = raw
        _ = stored
        verify_entered.set()
        await release_verify.wait()
        return True

    monkeypatch.setattr(app.state.auth_manager, '_verify_password', verify_after_barrier)
    login_task = asyncio.create_task(client.post('/v2/auth/login', json={'email': account.email, 'password': 'admin-pass-123'}))
    await verify_entered.wait()
    await AccountManager.update_account_status(
        account.id,
        UpdateAccountStatusParams(status=AccountStatus.DISABLED),
    )
    release_verify.set()

    response = await login_task

    assert response.status_code == 403
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    await account.refresh_from_db()
    assert account.role == AccountRole.USER
    assert account.status == AccountStatus.DISABLED
    assert await AuthSession.filter(account_id=account.id).count() == 0


@pytest.mark.anyio
async def test_allowlisted_password_login_rejects_changed_hash_snapshot(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await _create_password_user('admin@example.com', 'old-pass-123')
    verify_entered = asyncio.Event()
    release_verify = asyncio.Event()

    async def verify_after_barrier(raw: str, stored: str | None) -> bool:
        _ = raw
        _ = stored
        verify_entered.set()
        await release_verify.wait()
        return True

    monkeypatch.setattr(app.state.auth_manager, '_verify_password', verify_after_barrier)
    login_task = asyncio.create_task(client.post('/v2/auth/login', json={'email': account.email, 'password': 'old-pass-123'}))
    await verify_entered.wait()
    replacement_hash = hash_password('new-pass-123')
    await Account.filter(id=account.id).update(password_hash=replacement_hash)
    release_verify.set()

    response = await login_task

    assert response.status_code == 401
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    assert await AuthSession.filter(account_id=account.id).count() == 0
    await account.refresh_from_db()
    assert account.role == AccountRole.USER
    assert account.password_hash == replacement_hash


@pytest.mark.anyio
async def test_set_password_first_time_then_password_login(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')

    set_response = await client.post('/v2/auth/password', json={'new_password': 'fresh-pass-123'})
    assert assert_ok_response(set_response)['data'] == {'updated': True}

    await client.post('/v2/auth/logout')
    client.cookies.clear()

    login_response = await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'fresh-pass-123'})
    assert assert_ok_response(login_response)['data']['email'] == 'member@example.com'


@pytest.mark.anyio
async def test_set_password_change_requires_old_password(client: AsyncClient) -> None:
    await _create_password_user('member@example.com', 'old-pass-123')
    await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'old-pass-123'})
    client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE

    missing = await client.post('/v2/auth/password', json={'new_password': 'new-pass-123'})
    assert missing.status_code == 403

    wrong = await client.post('/v2/auth/password', json={'new_password': 'new-pass-123', 'old_password': 'bad-old'})
    assert wrong.status_code == 403

    ok = await client.post('/v2/auth/password', json={'new_password': 'new-pass-123', 'old_password': 'old-pass-123'})
    assert assert_ok_response(ok)['data'] == {'updated': True}


@pytest.mark.anyio
async def test_password_change_revokes_other_sessions_and_rotates_caller_session(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    await _create_password_user('member@example.com', 'old-pass-123')
    first_login = await client.post(
        '/v2/auth/login',
        json={'email': 'member@example.com', 'password': 'old-pass-123'},
    )
    first_cookie = first_login.cookies[SESSION_COOKIE_NAME]
    client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE

    async with asgi_client(app) as second_client:
        second_login = await second_client.post(
            '/v2/auth/login',
            json={'email': 'member@example.com', 'password': 'old-pass-123'},
        )
        second_client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE
        assert second_login.cookies[SESSION_COOKIE_NAME]
        assert await AuthSession.filter(revoked_at=None).count() == 2

        changed = await client.post(
            '/v2/auth/password',
            json={'new_password': 'new-pass-123', 'old_password': 'old-pass-123'},
        )

        assert assert_ok_response(changed)['data'] == {'updated': True}
        assert changed.cookies[SESSION_COOKIE_NAME] != first_cookie
        assert await AuthSession.filter(revoked_at=None).count() == 1
        assert (await second_client.get('/v2/auth/me')).status_code == 401
        assert (await client.get('/v2/auth/me')).status_code == 200


@pytest.mark.anyio
async def test_concurrent_password_changes_allow_one_valid_replacement_session(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_password_user('member@example.com', 'old-pass-123')
    await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'old-pass-123'})
    client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE

    async with asgi_client(app) as second_client:
        await second_client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'old-pass-123'})
        second_client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE

        hashes = {
            'first-new-pass': hash_password('first-new-pass'),
            'second-new-pass': hash_password('second-new-pass'),
        }
        entered = 0
        entered_lock = asyncio.Lock()
        both_entered = asyncio.Event()
        release = asyncio.Event()

        async def hash_after_barrier(raw: str) -> str:
            nonlocal entered
            async with entered_lock:
                entered += 1
                if entered == 2:
                    both_entered.set()
            await release.wait()
            return hashes[raw]

        monkeypatch.setattr(app.state.auth_manager, '_hash_password', hash_after_barrier)
        first_task = asyncio.create_task(
            client.post(
                '/v2/auth/password',
                json={'new_password': 'first-new-pass', 'old_password': 'old-pass-123'},
            )
        )
        second_task = asyncio.create_task(
            second_client.post(
                '/v2/auth/password',
                json={'new_password': 'second-new-pass', 'old_password': 'old-pass-123'},
            )
        )
        await asyncio.wait_for(both_entered.wait(), timeout=5)
        release.set()
        responses = await asyncio.gather(first_task, second_task)

        assert sorted(response.status_code for response in responses) == [200, 403]
        assert await AuthSession.filter(revoked_at=None).count() == 1
        successful_client = client if responses[0].status_code == 200 else second_client
        successful_response = responses[0] if responses[0].status_code == 200 else responses[1]
        assert successful_response.cookies.get(SESSION_COOKIE_NAME)
        assert (await successful_client.get('/v2/auth/me')).status_code == 200


@pytest.mark.anyio
async def test_password_change_is_rate_limited_per_authenticated_account(
    client: AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_password_user('member@example.com', 'old-pass-123')
    await client.post('/v2/auth/login', json={'email': 'member@example.com', 'password': 'old-pass-123'})
    client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE

    async def reject_password(raw: str, stored: str | None) -> bool:
        _ = raw
        _ = stored
        return False

    monkeypatch.setattr(app.state.auth_manager._password_worker, 'verify', reject_password)

    for _ in range(5):
        response = await client.post(
            '/v2/auth/password',
            json={'new_password': 'new-pass-123', 'old_password': 'wrong-pass-123'},
        )
        assert response.status_code == 403

    limited = await client.post(
        '/v2/auth/password',
        json={'new_password': 'new-pass-123', 'old_password': 'wrong-pass-123'},
    )
    assert limited.status_code == 429


@pytest.mark.anyio
async def test_password_endpoint_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        '/v2/auth/password',
        json={'new_password': 'fresh-pass-123'},
        headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_password_endpoint_rejects_missing_csrf_header(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')
    client.headers.pop(CSRF_HEADER_NAME)

    response = await client.post('/v2/auth/password', json={'new_password': 'fresh-pass-123'})

    assert response.status_code == 403
    assert response.json()['msg'] == 'CSRF validation failed.'


@pytest.mark.anyio
async def test_password_endpoint_rejects_disallowed_origin(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.post(
        '/v2/auth/password',
        json={'new_password': 'fresh-pass-123'},
        headers={'Origin': 'https://evil.example.test'},
    )

    assert response.status_code == 403
    assert response.json()['msg'] == 'CSRF validation failed.'


@pytest.mark.anyio
async def test_password_endpoint_accepts_allowed_origin(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')

    response = await client.post(
        '/v2/auth/password',
        json={'new_password': 'fresh-pass-123'},
        headers={'Origin': 'http://127.0.0.1:19341/'},
    )

    assert assert_ok_response(response)['data'] == {'updated': True}


@pytest.mark.anyio
async def test_safe_auth_request_does_not_require_csrf_header(client: AsyncClient) -> None:
    await Account.create(email='member@example.com')
    await login_with_google(client, 'member@example.com', sub='member-sub')
    client.headers.pop(CSRF_HEADER_NAME)

    response = await client.get('/v2/auth/me')

    assert response.status_code == 200


@pytest.mark.anyio
async def test_me_without_cookie_is_unauthorized(client: AsyncClient, auth_env: dict[str, object]) -> None:
    auth_env['APP_ENV'] = 'dev'

    response = await client.get('/v2/auth/me', headers={'origin': 'http://127.0.0.1:19341'})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_google_login_redirects_to_provider(client: AsyncClient) -> None:
    response = await client.get('/v2/auth/google/login', follow_redirects=False)

    assert response.status_code == 307
    location = response.headers['location']
    query = parse_qs(urlsplit(location).query)
    state = query['state'][0]
    assert location.startswith('https://accounts.google.com/o/oauth2/v2/auth?')
    assert 'client_id=client-id' in location
    assert 'redirect_uri=http%3A%2F%2Ftest%2Fv2%2Fauth%2Fgoogle%2Fcallback' in location
    assert query['code_challenge_method'] == ['S256']
    assert query['code_challenge'][0]
    assert 'code_verifier' not in query
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME)
    assert response.cookies[OAUTH_STATE_COOKIE_NAME] != state
    assert response.cookies[OAUTH_STATE_COOKIE_NAME].startswith(f'{state}.')
    assert 'httponly' in response.headers['set-cookie'].lower()


@pytest.mark.anyio
async def test_aurpay_login_redirects_to_provider(client: AsyncClient, auth_env: dict[str, object]) -> None:
    auth_env.update(
        {
            'AURPAY_OIDC_ISSUER': 'https://login.aurpay.test',
            'AURPAY_OIDC_CLIENT_ID': 'aurpay-client-id',
            'AURPAY_OIDC_REDIRECT_URI': 'http://test/v2/auth/aurpay/callback',
        }
    )

    response = await client.get('/v2/auth/aurpay/login', follow_redirects=False)

    assert response.status_code == 307
    location = response.headers['location']
    query = parse_qs(urlsplit(location).query)
    state = query['state'][0]
    assert location.startswith('https://login.aurpay.test/oauth2/authorize?')
    assert query['client_id'] == ['aurpay-client-id']
    assert query['redirect_uri'] == ['http://test/v2/auth/aurpay/callback']
    assert query['nonce'][0]
    assert query['code_challenge_method'] == ['S256']
    assert query['code_challenge'][0]
    assert 'code_verifier' not in query
    assert 'prompt' not in query
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME)
    assert response.cookies[OAUTH_STATE_COOKIE_NAME].startswith(f'{state}.')


@pytest.mark.anyio
async def test_aurpay_login_can_force_reauthentication(client: AsyncClient, auth_env: dict[str, object]) -> None:
    auth_env.update(
        {
            'AURPAY_OIDC_ISSUER': 'https://login.aurpay.test',
            'AURPAY_OIDC_CLIENT_ID': 'aurpay-client-id',
            'AURPAY_OIDC_REDIRECT_URI': 'http://test/v2/auth/aurpay/callback',
        }
    )

    response = await client.get('/v2/auth/aurpay/login', params={'prompt': 'login'}, follow_redirects=False)

    assert response.status_code == 307
    query = parse_qs(urlsplit(response.headers['location']).query)
    assert query['prompt'] == ['login']
    assert query['nonce'][0]
    assert query['code_challenge'][0]
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME)


@pytest.mark.anyio
async def test_aurpay_login_can_select_account(client: AsyncClient, auth_env: dict[str, object]) -> None:
    auth_env.update(
        {
            'AURPAY_OIDC_ISSUER': 'https://login.aurpay.test',
            'AURPAY_OIDC_CLIENT_ID': 'aurpay-client-id',
            'AURPAY_OIDC_REDIRECT_URI': 'http://test/v2/auth/aurpay/callback',
        }
    )

    response = await client.get('/v2/auth/aurpay/login', params={'prompt': 'select_account'}, follow_redirects=False)

    assert response.status_code == 307
    query = parse_qs(urlsplit(response.headers['location']).query)
    assert query['prompt'] == ['select_account']
    assert query['nonce'][0]
    assert query['code_challenge'][0]
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME)


@pytest.mark.anyio
async def test_aurpay_login_rejects_unsupported_prompt(client: AsyncClient) -> None:
    response = await client.get('/v2/auth/aurpay/login', params={'prompt': 'consent'}, follow_redirects=False)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_prod_google_login_state_cookie_uses_secure_flag(
    client: AsyncClient,
    auth_env: dict[str, object],
) -> None:
    auth_env['APP_ENV'] = 'prod'
    auth_env['CORS_ORIGINS'] = ['https://web.test']

    response = await client.get('/v2/auth/google/login', follow_redirects=False)

    assert response.status_code == 307
    assert 'secure' in response.headers['set-cookie'].lower()


@pytest.mark.anyio
async def test_google_callback_rejects_missing_state(client: AsyncClient) -> None:
    response = await client.get('/v2/auth/google/callback', params={'code': 'code:admin@example.com:admin-sub:Admin'})

    assert response.status_code == 303
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Invalid+login+state.'
    assert response.cookies.get('rpc_gateway_session') is None


@pytest.mark.anyio
async def test_google_callback_rejects_mismatched_state(client: AsyncClient) -> None:
    await start_google_login(client)

    response = await client.get(
        '/v2/auth/google/callback',
        params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': 'wrong-state'},
    )

    assert response.status_code == 303
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Invalid+login+state.'
    assert response.cookies.get('rpc_gateway_session') is None
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME) is None


@pytest.mark.anyio
async def test_google_callback_rejects_tampered_state_cookie(client: AsyncClient) -> None:
    state = await start_google_login(client)
    cookie_value = client.cookies[OAUTH_STATE_COOKIE_NAME]
    client.cookies.set(OAUTH_STATE_COOKIE_NAME, f'{cookie_value}tampered')

    response = await client.get(
        '/v2/auth/google/callback',
        params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': state},
    )

    assert response.status_code == 303
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Invalid+login+state.'
    assert response.cookies.get('rpc_gateway_session') is None
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME) is None


@pytest.mark.anyio
async def test_disable_waits_for_google_login_and_revokes_session(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='member@example.com', status=AccountStatus.ACTIVE)
    await Auth.create(account_id=account.id, provider=AuthProvider.GOOGLE, identifier='member-sub')
    update_entered = asyncio.Event()
    release_update = asyncio.Event()
    update_login = auth_service.AuthManager._update_user_login

    async def update_after_barrier(
        locked_account: Account,
        values: auth_service._LoginValues,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        update_entered.set()
        await release_update.wait()
        await update_login(locked_account, values, using_db=using_db)

    monkeypatch.setattr(auth_service.AuthManager, '_update_user_login', staticmethod(update_after_barrier))
    state = await start_google_login(client)
    login_task = asyncio.create_task(
        client.get(
            '/v2/auth/google/callback',
            params={'code': 'code:member@example.com:member-sub:Member', 'state': state},
        )
    )
    await update_entered.wait()

    disable_started = asyncio.Event()

    async def disable_account() -> None:
        disable_started.set()
        await AccountManager.update_account_status(
            account.id,
            UpdateAccountStatusParams(status=AccountStatus.DISABLED),
        )

    disable_task = asyncio.create_task(disable_account())
    await disable_started.wait()
    done, _pending = await asyncio.wait({disable_task}, timeout=0.1)
    disable_blocked = not done
    release_update.set()
    login_response, _ = await asyncio.gather(login_task, disable_task)

    assert disable_blocked
    assert login_response.status_code == 303
    assert login_response.headers['location'] == 'http://web.test/zh/auth/callback'
    await account.refresh_from_db()
    assert account.status == AccountStatus.DISABLED
    assert await AuthSession.filter(account_id=account.id, revoked_at=None).count() == 0


@pytest.mark.anyio
async def test_archive_waits_for_google_binding_and_removes_it(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='member@example.com', status=AccountStatus.ACTIVE)
    bind_entered = asyncio.Event()
    release_bind = asyncio.Event()
    bind_auth = auth_service.AuthManager._bind_user_google_auth

    async def bind_after_barrier(
        account_id: str,
        google_sub: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        bind_entered.set()
        await release_bind.wait()
        await bind_auth(account_id, google_sub, using_db=using_db)

    monkeypatch.setattr(auth_service.AuthManager, '_bind_user_google_auth', staticmethod(bind_after_barrier))
    state = await start_google_login(client)
    login_task = asyncio.create_task(
        client.get(
            '/v2/auth/google/callback',
            params={'code': 'code:member@example.com:member-sub:Member', 'state': state},
        )
    )
    await bind_entered.wait()

    archive_started = asyncio.Event()

    async def archive_account() -> None:
        archive_started.set()
        await AccountManager.archive_accounts(ArchiveAccountsParams(ids=[account.id]))

    archive_task = asyncio.create_task(archive_account())
    await archive_started.wait()
    done, _pending = await asyncio.wait({archive_task}, timeout=0.1)
    archive_blocked = not done
    release_bind.set()
    login_response, _ = await asyncio.gather(login_task, archive_task)

    assert archive_blocked
    assert login_response.status_code == 303
    assert login_response.headers['location'] == 'http://web.test/zh/auth/callback'
    await account.refresh_from_db()
    assert account.status == AccountStatus.ARCHIVED
    assert account.deleted_at is not None
    assert await Auth.filter(account_id=account.id, deleted_at=None).count() == 0
    assert await AuthSession.filter(account_id=account.id, revoked_at=None).count() == 0


@pytest.mark.anyio
async def test_prod_login_cookie_uses_secure_flag_from_config(
    client: AsyncClient, auth_env: dict[str, object], auth_log: CapturingLog
) -> None:
    state = await start_google_login(client)
    auth_env['APP_ENV'] = 'prod'
    auth_env['CORS_ORIGINS'] = ['https://web.test']

    response = await client.get(
        '/v2/auth/google/callback', params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': state}
    )

    assert response.status_code == 303, response.text
    assert response.headers['location'] == 'http://web.test/zh/auth/callback'
    assert 'secure' in response.headers['set-cookie'].lower()
    admin = await Account.get(email='admin@example.com')
    assert admin.role == AccountRole.ADMIN
    assert admin.status == AccountStatus.ACTIVE
    assert auth_log.records[-1]['level'] == 'info'
    assert auth_log.records[-1]['message'].startswith('Admin login succeeded | ')
    assert 'Admin:' in auth_log.records[-1]['message']
    assert 'Created:True' in auth_log.records[-1]['message']
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
@pytest.mark.parametrize('account_status', [AccountStatus.DISABLED, AccountStatus.ARCHIVED])
async def test_google_login_does_not_reactivate_inactive_admin(
    client: AsyncClient,
    account_status: AccountStatus,
) -> None:
    admin = await Account.create(
        email='admin@example.com',
        role=AccountRole.ADMIN,
        status=account_status,
    )
    state = await start_google_login(client)

    response = await client.get(
        '/v2/auth/google/callback',
        params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': state},
    )

    assert response.status_code == 303
    assert response.headers['location'].endswith('error=Account+is+not+allowed+to+login.')
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    await admin.refresh_from_db()
    assert admin.role == AccountRole.ADMIN
    assert admin.status == account_status


@pytest.mark.anyio
async def test_allowlisted_user_disable_wins_google_login(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='admin@example.com', status=AccountStatus.ACTIVE)
    await Auth.create(account_id=account.id, provider=AuthProvider.GOOGLE, identifier='admin-sub')
    auth_read = asyncio.Event()
    release_auth = asyncio.Event()
    get_google_auth = auth_service.AuthManager._get_google_auth

    async def get_auth_after_barrier(google_sub: str) -> Auth | None:
        auth = await get_google_auth(google_sub)
        auth_read.set()
        await release_auth.wait()
        return auth

    monkeypatch.setattr(auth_service.AuthManager, '_get_google_auth', staticmethod(get_auth_after_barrier))
    state = await start_google_login(client)
    login_task = asyncio.create_task(
        client.get(
            '/v2/auth/google/callback',
            params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': state},
        )
    )
    await auth_read.wait()
    await AccountManager.update_account_status(
        account.id,
        UpdateAccountStatusParams(status=AccountStatus.DISABLED),
    )
    release_auth.set()

    response = await login_task

    assert response.status_code == 303
    assert response.headers['location'].endswith('error=Account+is+not+allowed+to+login.')
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    await account.refresh_from_db()
    assert account.role == AccountRole.USER
    assert account.status == AccountStatus.DISABLED
    assert await AuthSession.filter(account_id=account.id).count() == 0


@pytest.mark.anyio
async def test_allowlisted_user_archive_wins_first_google_binding(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='admin@example.com', status=AccountStatus.ACTIVE)
    lock_entered = asyncio.Event()
    release_lock = asyncio.Event()
    lock_admin = auth_service.AuthManager._lock_admin_account

    async def lock_after_barrier(
        account_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> Account | None:
        lock_entered.set()
        await release_lock.wait()
        return await lock_admin(account_id, using_db=using_db)

    monkeypatch.setattr(auth_service.AuthManager, '_lock_admin_account', staticmethod(lock_after_barrier))
    state = await start_google_login(client)
    login_task = asyncio.create_task(
        client.get(
            '/v2/auth/google/callback',
            params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': state},
        )
    )
    await lock_entered.wait()
    await AccountManager.archive_accounts(ArchiveAccountsParams(ids=[account.id]))
    release_lock.set()

    response = await login_task

    assert response.status_code == 303
    assert response.headers['location'].endswith('error=Google+account+is+not+allowed.')
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    await account.refresh_from_db()
    assert account.role == AccountRole.USER
    assert account.status == AccountStatus.ARCHIVED
    assert account.deleted_at is not None
    assert await Auth.filter(account_id=account.id, deleted_at=None).count() == 0
    assert await AuthSession.filter(account_id=account.id).count() == 0


@pytest.mark.anyio
async def test_concurrent_first_admin_google_logins_reuse_created_account(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_entered = 0
    create_lock = asyncio.Lock()
    both_entered = asyncio.Event()
    release_create = asyncio.Event()
    create_admin = auth_service.AuthManager._create_admin

    async def create_after_barrier(
        email: str,
        values: auth_service._LoginValues,
    ) -> tuple[Account, bool]:
        nonlocal create_entered
        async with create_lock:
            create_entered += 1
            if create_entered == 2:
                both_entered.set()
        await release_create.wait()
        return await create_admin(email, values)

    monkeypatch.setattr(auth_service.AuthManager, '_create_admin', staticmethod(create_after_barrier))
    async with (
        asgi_client(app) as first_client,
        asgi_client(app) as second_client,
    ):
        first_state = await start_google_login(first_client)
        second_state = await start_google_login(second_client)
        first_task = asyncio.create_task(
            first_client.get(
                '/v2/auth/google/callback',
                params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': first_state},
            )
        )
        second_task = asyncio.create_task(
            second_client.get(
                '/v2/auth/google/callback',
                params={'code': 'code:admin@example.com:admin-sub:Admin', 'state': second_state},
            )
        )
        await both_entered.wait()
        release_create.set()
        first_response, second_response = await asyncio.gather(first_task, second_task)

    assert first_response.headers['location'] == 'http://web.test/zh/auth/callback'
    assert second_response.headers['location'] == 'http://web.test/zh/auth/callback'
    admin = await Account.get(email='admin@example.com')
    assert admin.role == AccountRole.ADMIN
    assert admin.status == AccountStatus.ACTIVE
    assert await Auth.filter(account_id=admin.id, provider=AuthProvider.GOOGLE, deleted_at=None).count() == 1
    assert await AuthSession.filter(account_id=admin.id, revoked_at=None).count() == 2


@pytest.mark.anyio
async def test_google_exchange_failure_returns_auth_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, auth_log: CapturingLog
) -> None:
    async def fail_exchange(self: object, code: str, code_verifier: str) -> None:
        _ = self
        _ = code
        _ = code_verifier
        request = httpx.Request('POST', 'https://oauth2.googleapis.com/token')
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError('invalid_grant', request=request, response=response)

    monkeypatch.setattr('app.services.auth.auth.AuthManager._fetch_google_profile', fail_exchange)

    state = await start_google_login(client)
    response = await client.get('/v2/auth/google/callback', params={'code': 'expired-code', 'state': state})

    assert response.status_code == 303
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Google+login+failed.'
    assert auth_log.records[-1] == {
        'level': 'warning',
        'message': 'Google OAuth exchange failed',
    }
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_google_callback_redirects_provider_error_to_frontend(client: AsyncClient) -> None:
    state = await start_google_login(client)
    response = await client.get('/v2/auth/google/callback', params={'error': 'access_denied', 'state': state})

    assert response.status_code == 303
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Google+login+failed%3A+access_denied'


@pytest.mark.anyio
async def test_google_callback_redirects_missing_code_to_frontend(client: AsyncClient) -> None:
    state = await start_google_login(client)
    response = await client.get('/v2/auth/google/callback', params={'state': state})

    assert response.status_code == 303
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Google+login+code+is+missing.'


@pytest.mark.anyio
async def test_user_first_google_login_activates_local_record(client: AsyncClient, auth_log: CapturingLog) -> None:
    user = await Account.create(email='member@example.com')

    await login_with_google(client, 'member@example.com', sub='member-sub', name='Member Account')

    user = await Account.get(id=user.id)
    assert user.status == AccountStatus.ACTIVE
    auth = await Auth.get(account_id=user.id, provider=AuthProvider.GOOGLE)
    assert auth.identifier == 'member-sub'
    assert user.name == 'Member Account'
    assert user.avatar_url == 'https://example.com/avatar.png'
    assert user.first_login_at is not None
    assert user.last_login_at is not None

    response = await client.get('/v2/auth/me')
    data = assert_ok_response(response)['data']
    assert data['identity_type'] == 'user'
    assert data['email'] == 'member@example.com'
    assert auth_log.records[-1]['level'] == 'info'
    assert auth_log.records[-1]['message'] == f'New user | Account:{user.id} | Login:Google'
    notification = next(record for record in auth_log.records if record.get('extra') == {'send_msg': True})
    assert notification['message'] == f'New user | Account:{user.id} | Login:Google'
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_unknown_google_email_is_rejected(client: AsyncClient, auth_log: CapturingLog) -> None:
    state = await start_google_login(client)
    response = await client.get(
        '/v2/auth/google/callback', params={'code': 'code:missing@example.com:sub:Missing', 'state': state}
    )

    assert response.status_code == 303, response.text
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Google+account+is+not+allowed.'
    assert auth_log.records[-1] == {
        'level': 'warning',
        'message': 'Local account not found',
    }
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_bound_user_rejects_same_email_with_different_google_sub(client: AsyncClient, auth_log: CapturingLog) -> None:
    account = await Account.create(email='member@example.com', status=AccountStatus.ACTIVE)
    await Auth.create(account_id=account.id, provider=AuthProvider.GOOGLE, identifier='bound-sub')

    state = await start_google_login(client)
    response = await client.get(
        '/v2/auth/google/callback', params={'code': 'code:member@example.com:other-sub:Member', 'state': state}
    )

    assert response.status_code == 303, response.text
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Google+account+is+not+allowed.'
    assert auth_log.records[-1]['level'] == 'warning'
    assert auth_log.records[-1]['message'].startswith('Google identity mismatch | ')
    assert 'Account:' in auth_log.records[-1]['message']
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_bound_admin_rejects_same_email_with_different_google_sub(client: AsyncClient, auth_log: CapturingLog) -> None:
    account = await Account.create(
        email='admin@example.com',
        role=AccountRole.ADMIN,
        status=AccountStatus.ACTIVE,
    )
    await Auth.create(account_id=account.id, provider=AuthProvider.GOOGLE, identifier='bound-admin-sub')

    state = await start_google_login(client)
    response = await client.get(
        '/v2/auth/google/callback', params={'code': 'code:admin@example.com:other-sub:Admin', 'state': state}
    )

    assert response.status_code == 303, response.text
    assert response.headers['location'] == 'http://web.test/zh/auth/callback?error=Google+account+is+not+allowed.'
    assert auth_log.records[-1]['level'] == 'warning'
    assert auth_log.records[-1]['message'].startswith('Google identity mismatch | ')
    assert 'Admin:' in auth_log.records[-1]['message']
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_admin_session_fails_after_email_removed_from_whitelist(
    client: AsyncClient, auth_env: dict[str, object], auth_log: CapturingLog
) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    assert await AuthSession.filter(revoked_at__isnull=True).count() == 1

    auth_env['ADMIN_ALLOWED_EMAILS'] = ['other@example.com']
    response = await client.get('/v2/auth/me')

    assert response.status_code == 401
    assert await AuthSession.filter(revoked_at__isnull=False).count() == 1
    assert auth_log.records[-1]['level'] == 'warning'
    assert auth_log.records[-1]['message'].startswith('Admin email is not allowed | ')
    assert 'Admin:' in auth_log.records[-1]['message']
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_inactive_user_session_revoke_logs_without_email(client: AsyncClient, auth_log: CapturingLog) -> None:
    user = await Account.create(email='member@example.com')
    user_cookie = await login_with_google(client, 'member@example.com', sub='member-sub')
    await user.update_from_dict({'status': AccountStatus.DISABLED}).save()
    client.cookies.set('rpc_gateway_session', user_cookie)

    response = await client.get('/v2/auth/me')

    assert response.status_code == 401
    assert auth_log.records[-1] == {
        'level': 'warning',
        'message': f'Account session is invalid | Account:{user.id} | Status:disabled',
    }
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_logout_logs_session_revocation_without_sensitive_values(client: AsyncClient, auth_log: CapturingLog) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub')

    response = await client.post('/v2/auth/logout')

    assert_ok_response(response)
    assert auth_log.records[-1]['level'] == 'info'
    assert auth_log.records[-1]['message'].startswith('Session logged out | ')
    assert 'Identity:admin' in auth_log.records[-1]['message']
    assert_log_has_no_sensitive_auth_values(auth_log)


@pytest.mark.anyio
async def test_logout_rejects_missing_csrf_header(client: AsyncClient) -> None:
    await login_with_google(client, 'admin@example.com', sub='admin-sub')
    client.headers.pop(CSRF_HEADER_NAME)

    response = await client.post('/v2/auth/logout')

    assert response.status_code == 403
    assert response.json()['msg'] == 'CSRF validation failed.'
    assert await AuthSession.filter(revoked_at__isnull=True).count() == 1


@pytest.mark.anyio
async def test_logout_without_session_remains_idempotent(client: AsyncClient) -> None:
    response = await client.post('/v2/auth/logout')

    assert assert_ok_response(response)['data'] == {'logged_out': True}
