from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.core.config import Config
from app.services.auth import GoogleProfile
from app.services.auth.csrf import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.services.auth.session import OAUTH_STATE_COOKIE_NAME
from httpx import AsyncClient


async def start_google_login(client: AsyncClient) -> str:
    response = await client.get('/v2/auth/google/login', follow_redirects=False)
    assert response.status_code == 307, response.text
    state = parse_qs(urlsplit(response.headers['location']).query)['state'][0]
    assert response.cookies.get(OAUTH_STATE_COOKIE_NAME)
    return state


async def login_with_google(client: AsyncClient, email: str, sub: str = 'google-sub', name: str = 'Test Account') -> str:
    state = await start_google_login(client)
    response = await client.get('/v2/auth/google/callback', params={'code': f'code:{email}:{sub}:{name}', 'state': state})
    assert response.status_code == 303, response.text
    cookie = response.cookies.get('rpc_gateway_session')
    assert cookie
    client.headers[CSRF_HEADER_NAME] = CSRF_HEADER_VALUE
    return cookie


async def fake_google_exchange(self: Any, code: str, code_verifier: str) -> GoogleProfile:
    _ = self
    assert code_verifier
    _, email, sub, name = code.split(':', 3)
    return GoogleProfile(
        sub=sub,
        email=email,
        email_verified=True,
        name=name,
        avatar_url='https://example.com/avatar.png',
    )


def configure_auth_settings(monkeypatch: Any) -> dict[str, Any]:
    state = {
        'APP_ENV': 'test',
        'GOOGLE_OAUTH_CLIENT_ID': 'client-id',
        'GOOGLE_OAUTH_CLIENT_SECRET': 'client-secret',
        'GOOGLE_OAUTH_REDIRECT_URI': 'http://test/v2/auth/google/callback',
        'FRONTEND_AUTH_CALLBACK_URL': 'http://web.test/en/auth/callback',
        'CORS_ORIGINS': ['http://127.0.0.1:19341', 'http://localhost:19341'],
        'ADMIN_ALLOWED_EMAILS': ['admin@example.com'],
        'AUTH_SESSION_SECRET': 'test-session-secret-value-32-bytes',
        'AUTH_PAT_HASH_SECRET': 'test-pat-hash-secret-value-32-bytes',
        'AUTH_COOKIE_SAMESITE': 'lax',
        'AUTH_COOKIE_SECURE': None,
        'ENDPOINT_KEYRING': {'v1': 'test-endpoint-encryption-key-32-bytes'},
    }

    def fake_get_conf() -> Config:
        return Config.model_validate(state)

    monkeypatch.setattr('app.services.auth.settings.get_conf', fake_get_conf)
    return state
