import hashlib
from urllib.parse import urlsplit, urlunsplit

from fastapi import Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from pyrate_limiter import Duration, Rate

from app.api import BaseRouter, PublicRouter
from app.api.deps import AuthIdentityDep, AuthManagerDep, LogoutCsrfDep, OAuthStateCookieValue, SessionCookieValue
from app.api.v2.auth.cookie import (
    delete_oauth_state_cookie,
    delete_session_cookie,
    set_oauth_state_cookie,
    set_session_cookie,
)
from app.core import context
from app.core.errors import APIError
from app.middleware.limiter import RedisRateLimiter
from app.model.account.account import normalize_email
from app.model.auth import (
    AuthIdentity,
    LoginResult,
    LogoutResult,
    PasswordLoginParams,
    PasswordResult,
    SetPasswordParams,
)
from app.services.auth import AuthManager
from app.services.auth.session import build_oauth_login_state, parse_oauth_state_cookie
from app.services.auth.settings import get_auth_settings

router = BaseRouter(route_class=PublicRouter)

password_login_rate_limit = RedisRateLimiter(rates=[Rate(10, Duration.MINUTE)], bucket_key='auth-password-login')
password_login_identity_rate_limit = RedisRateLimiter(
    rates=[Rate(5, Duration.MINUTE)],
    bucket_key='auth-password-login-identity',
)
password_change_ip_rate_limit = RedisRateLimiter(
    rates=[Rate(10, Duration.MINUTE)],
    bucket_key='auth-password-change-ip',
)
password_change_account_rate_limit = RedisRateLimiter(
    rates=[Rate(5, Duration.MINUTE)],
    bucket_key='auth-password-change-account',
)
password_change_session_rate_limit = RedisRateLimiter(
    rates=[Rate(5, Duration.MINUTE)],
    bucket_key='auth-password-change-session',
)


def _opaque_rate_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _auth_callback_redirect(frontend_callback_url: str | None = None, error: str | None = None) -> RedirectResponse:
    response = RedirectResponse(
        AuthManager.build_auth_callback_url(error=error, frontend_auth_callback_url=frontend_callback_url),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    delete_oauth_state_cookie(response)
    return response


def _origin(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, '', '', '')).rstrip('/')


def _callback_path_from_referer(referer: str | None) -> str:
    if referer is None:
        return urlsplit(get_auth_settings().frontend_auth_callback_url).path
    parts = urlsplit(referer)
    path = parts.path.rstrip('/')
    if path.endswith('/login'):
        prefix = path.removesuffix('/login')
        return f'{prefix}/auth/callback' if prefix else '/auth/callback'
    return urlsplit(get_auth_settings().frontend_auth_callback_url).path


def _frontend_callback_url(request: Request) -> str:
    settings = get_auth_settings()
    fallback_url = settings.frontend_auth_callback_url
    fallback_origin = _origin(fallback_url)
    allowed_origins = set(settings.allowed_frontend_origins)
    if fallback_origin is not None:
        allowed_origins.add(fallback_origin)

    referer = request.headers.get('referer')
    candidate_origin = _origin(referer) or _origin(request.headers.get('origin'))
    if candidate_origin is None or candidate_origin not in allowed_origins:
        return fallback_url

    callback_path = _callback_path_from_referer(referer)
    return f'{candidate_origin}{callback_path}'


@router.get(
    '/google/login',
    response_model=None,
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    responses={status.HTTP_307_TEMPORARY_REDIRECT: {'description': 'Temporary Redirect'}},
)
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the browser to Google OAuth."""
    login_state = build_oauth_login_state(_frontend_callback_url(request))
    response = RedirectResponse(
        AuthManager.build_google_login_url(login_state),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    set_oauth_state_cookie(response, login_state.cookie_value)
    return response


@router.get(
    '/google/callback',
    response_model=None,
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    responses={status.HTTP_303_SEE_OTHER: {'description': 'See Other'}},
)
async def google_callback(
    request: Request,
    auth_manager: AuthManagerDep,
    rpc_gateway_oauth_state: OAuthStateCookieValue = None,
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Handle the Google OAuth callback and set the session cookie."""
    oauth_state = parse_oauth_state_cookie(state, rpc_gateway_oauth_state)
    if oauth_state is None:
        return _auth_callback_redirect(error='Invalid login state.')
    if error:
        return _auth_callback_redirect(oauth_state.frontend_callback_url, error=f'Google login failed: {error}')
    if not code:
        return _auth_callback_redirect(oauth_state.frontend_callback_url, error='Google login code is missing.')

    try:
        login = await auth_manager.login_with_google(
            code,
            oauth_state.code_verifier,
            client_ip=context.client_ip(request),
            user_agent=request.headers.get('user-agent'),
        )
    except APIError as exc:
        return _auth_callback_redirect(oauth_state.frontend_callback_url, error=exc.msg)

    response = _auth_callback_redirect(oauth_state.frontend_callback_url)
    set_session_cookie(response, login.session.cookie_value)
    return response


@router.post('/login', response_model=LoginResult, dependencies=[Depends(password_login_rate_limit)])
async def password_login(
    request: Request,
    response: Response,
    params: PasswordLoginParams,
    auth_manager: AuthManagerDep,
) -> LoginResult:
    """Authenticate with an email and password and set the session cookie.

    Rate limited per trusted client IP and normalized login identity to slow credential stuffing.
    """
    identity_key = _opaque_rate_key(normalize_email(params.email))
    await password_login_identity_rate_limit.acquire(request, response, identity_key)
    login = await auth_manager.login_with_password(
        params.email,
        params.password,
        client_ip=context.client_ip(request),
        user_agent=request.headers.get('user-agent'),
    )
    set_session_cookie(response, login.session.cookie_value)
    return login.result


@router.post('/password', response_model=PasswordResult, dependencies=[Depends(password_change_ip_rate_limit)])
async def set_password(
    request: Request,
    response: Response,
    params: SetPasswordParams,
    identity: AuthIdentityDep,
    auth_manager: AuthManagerDep,
    rpc_gateway_session: SessionCookieValue,
) -> PasswordResult:
    """Set or change the password of the authenticated account.

    old_password is required only when a password already exists.
    """
    account_key = _opaque_rate_key(identity.id)
    await password_change_account_rate_limit.acquire(request, response, account_key)
    session_key = _opaque_rate_key(rpc_gateway_session or '')
    await password_change_session_rate_limit.acquire(request, response, session_key)
    session = await auth_manager.set_password(
        identity.id,
        params,
        identity_type=identity.identity_type,
        ip=context.client_ip(request),
        user_agent=request.headers.get('user-agent'),
    )
    set_session_cookie(response, session.cookie_value)
    return PasswordResult(updated=True)


@router.get('/me', response_model=AuthIdentity)
async def me(identity: AuthIdentityDep) -> AuthIdentity:
    """Return the authenticated identity."""
    return identity


@router.post('/logout', response_model=LogoutResult)
async def logout(
    response: Response,
    csrf: LogoutCsrfDep,
    rpc_gateway_session: SessionCookieValue,
    auth_manager: AuthManagerDep,
) -> LogoutResult:
    """Revoke the session and clear its cookie."""
    await auth_manager.logout(rpc_gateway_session)
    delete_session_cookie(response)
    return LogoutResult(logged_out=True)
