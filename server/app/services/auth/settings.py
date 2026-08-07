from dataclasses import dataclass
from typing import Literal

from app.core.config import Config, get_conf


@dataclass(frozen=True)
class AuthSettings:
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    frontend_auth_callback_url: str
    allowed_frontend_origins: frozenset[str]
    admin_allowed_emails: frozenset[str]
    session_secret: str
    cookie_samesite: Literal['lax', 'strict', 'none']
    cookie_secure: bool
    is_dev: bool
    session_ttl_seconds: int = 259200


def _cookie_secure(conf: Config) -> bool:
    if conf.AUTH_COOKIE_SECURE is not None:
        return conf.AUTH_COOKIE_SECURE
    return conf.APP_ENV == 'prod' or conf.AUTH_COOKIE_SAMESITE == 'none'


def get_auth_settings(conf: Config | None = None) -> AuthSettings:
    conf = conf or get_conf()
    allowed = {email.strip().lower() for email in conf.ADMIN_ALLOWED_EMAILS if email.strip()}
    allowed_origins = {origin.strip().rstrip('/') for origin in conf.CORS_ORIGINS if origin.strip() and origin != '*'}
    return AuthSettings(
        google_client_id=conf.GOOGLE_OAUTH_CLIENT_ID,
        google_client_secret=conf.GOOGLE_OAUTH_CLIENT_SECRET,
        google_redirect_uri=conf.GOOGLE_OAUTH_REDIRECT_URI,
        frontend_auth_callback_url=conf.FRONTEND_AUTH_CALLBACK_URL,
        allowed_frontend_origins=frozenset(allowed_origins),
        admin_allowed_emails=frozenset(allowed),
        session_secret=conf.AUTH_SESSION_SECRET,
        cookie_samesite=conf.AUTH_COOKIE_SAMESITE,
        cookie_secure=_cookie_secure(conf),
        is_dev=conf.is_dev,
    )
