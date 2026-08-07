import pytest
from app.api import deps
from app.core.errors import ForbiddenError
from app.services.auth import csrf
from app.services.auth.settings import AuthSettings
from starlette.requests import Request


def _settings() -> AuthSettings:
    return AuthSettings(
        google_client_id='',
        google_client_secret='',
        google_redirect_uri='',
        frontend_auth_callback_url='',
        allowed_frontend_origins=frozenset({'https://console.example.test'}),
        admin_allowed_emails=frozenset(),
        session_secret='s' * 32,
        cookie_samesite='lax',
        cookie_secure=True,
        is_dev=False,
    )


def _request(method: str, headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            'type': 'http',
            'method': method,
            'path': '/v2/apps',
            'headers': [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
            'client': ('127.0.0.1', 12345),
            'server': ('testserver', 80),
            'scheme': 'http',
            'query_string': b'',
        }
    )


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csrf, 'get_auth_settings', _settings)


@pytest.mark.parametrize('method', ['GET', 'HEAD', 'OPTIONS'])
def test_safe_request_does_not_require_csrf(method: str) -> None:
    csrf.validate_csrf_request(_request(method))


@pytest.mark.parametrize('header_value', [None, '', '0', 'true'])
def test_write_request_requires_exact_csrf_header(header_value: str | None) -> None:
    headers = {} if header_value is None else {csrf.CSRF_HEADER_NAME: header_value}

    with pytest.raises(ForbiddenError, match='CSRF validation failed'):
        csrf.validate_csrf_request(_request('POST', headers))


def test_write_request_without_origin_accepts_csrf_header() -> None:
    csrf.validate_csrf_request(_request('POST', {csrf.CSRF_HEADER_NAME: csrf.CSRF_HEADER_VALUE}))


def test_write_request_accepts_normalized_allowed_origin() -> None:
    csrf.validate_csrf_request(
        _request(
            'POST',
            {
                csrf.CSRF_HEADER_NAME: csrf.CSRF_HEADER_VALUE,
                'Origin': 'https://console.example.test:443/',
            },
        )
    )


@pytest.mark.parametrize('origin', ['https://evil.example.test', 'null', 'https://console.example.test/path'])
def test_write_request_rejects_unlisted_or_invalid_origin(origin: str) -> None:
    with pytest.raises(ForbiddenError, match='CSRF validation failed'):
        csrf.validate_csrf_request(
            _request(
                'POST',
                {
                    csrf.CSRF_HEADER_NAME: csrf.CSRF_HEADER_VALUE,
                    'Origin': origin,
                },
            )
        )


def test_logout_without_session_does_not_require_csrf() -> None:
    deps.validate_logout_csrf(_request('POST'), None)


def test_logout_with_session_requires_csrf() -> None:
    with pytest.raises(ForbiddenError, match='CSRF validation failed'):
        deps.validate_logout_csrf(_request('POST'), 'user.session-token')
