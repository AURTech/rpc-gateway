from fastapi import Response

from app.services.auth.session import OAUTH_STATE_COOKIE_NAME, OAUTH_STATE_TTL_SECONDS, SESSION_COOKIE_NAME
from app.services.auth.settings import get_auth_settings


def set_session_cookie(response: Response, value: str) -> None:
    settings = get_auth_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=value,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path='/',
    )


def set_oauth_state_cookie(response: Response, value: str) -> None:
    settings = get_auth_settings()
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=value,
        max_age=OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path='/',
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')


def delete_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path='/')
