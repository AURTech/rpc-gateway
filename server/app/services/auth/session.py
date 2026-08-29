import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import datetime, timedelta

from tortoise.backends.base.client import BaseDBAsyncClient

from app.model.auth import IdentityType
from app.orm.auth import AuthSession
from app.services.auth.settings import get_auth_settings
from app.util import datetime as datetime_util

SESSION_COOKIE_NAME = 'rpc_gateway_session'
OAUTH_STATE_COOKIE_NAME = 'rpc_gateway_oauth_state'
OAUTH_STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class OAuthLoginState:
    state: str
    cookie_value: str
    code_verifier: str
    code_challenge: str
    nonce: str


@dataclass(frozen=True)
class ParsedOAuthState:
    code_verifier: str
    frontend_callback_url: str
    nonce: str


@dataclass(frozen=True)
class IssuedSession:
    cookie_value: str
    expires_at: datetime


def _sign_value(value: str) -> str:
    secret = get_auth_settings().session_secret.encode()
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def hash_session_token(token: str) -> str:
    secret = get_auth_settings().session_secret.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def _encode_callback_url(value: str) -> str:
    return urlsafe_b64encode(value.encode()).decode().rstrip('=')


def _decode_callback_url(value: str) -> str | None:
    if not value:
        return None
    padding = '=' * (-len(value) % 4)
    try:
        return urlsafe_b64decode(f'{value}{padding}').decode()
    except (BinasciiError, UnicodeDecodeError, ValueError):
        return None


def build_oauth_login_state(frontend_callback_url: str | None = None) -> OAuthLoginState:
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    challenge_digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = urlsafe_b64encode(challenge_digest).decode().rstrip('=')
    nonce = secrets.token_urlsafe(32)
    callback_url = frontend_callback_url or get_auth_settings().frontend_auth_callback_url
    payload = f'{state}.{code_verifier}.{nonce}.{_encode_callback_url(callback_url)}'
    return OAuthLoginState(
        state=state,
        cookie_value=f'{payload}.{_sign_value(payload)}',
        code_verifier=code_verifier,
        code_challenge=code_challenge,
        nonce=nonce,
    )


def parse_oauth_state_cookie(state: str | None, cookie_value: str | None) -> ParsedOAuthState | None:
    if not state or not cookie_value:
        return None
    parts = cookie_value.split('.')
    if len(parts) != 5:
        return None
    cookie_state, code_verifier, nonce, encoded_callback_url, signature = parts
    frontend_callback_url = _decode_callback_url(encoded_callback_url)
    if not hmac.compare_digest(cookie_state, state):
        return None
    if not code_verifier or not frontend_callback_url or not signature:
        return None
    payload = '.'.join(parts[:-1])
    if not hmac.compare_digest(signature, _sign_value(payload)):
        return None
    return ParsedOAuthState(code_verifier=code_verifier, frontend_callback_url=frontend_callback_url, nonce=nonce)


def split_cookie_value(value: str) -> tuple[IdentityType, str] | None:
    prefix, sep, token = value.partition('.')
    if sep != '.' or not token:
        return None
    if prefix == 'admin':
        return IdentityType.ADMIN, token
    if prefix == 'user':
        return IdentityType.USER, token
    return None


async def issue_admin_session(admin_id: str, *, using_db: BaseDBAsyncClient | None = None) -> IssuedSession:
    token = secrets.token_urlsafe(32)
    expires_at = datetime_util.now_utc() + timedelta(seconds=get_auth_settings().session_ttl_seconds)
    await AuthSession.create(
        using_db=using_db,
        account_id=admin_id,
        token_hash=hash_session_token(token),
        expires_at=expires_at,
    )
    return IssuedSession(cookie_value=f'admin.{token}', expires_at=expires_at)


async def issue_user_session(account_id: str, *, using_db: BaseDBAsyncClient | None = None) -> IssuedSession:
    token = secrets.token_urlsafe(32)
    expires_at = datetime_util.now_utc() + timedelta(seconds=get_auth_settings().session_ttl_seconds)
    await AuthSession.create(
        using_db=using_db,
        account_id=account_id,
        token_hash=hash_session_token(token),
        expires_at=expires_at,
    )
    return IssuedSession(cookie_value=f'user.{token}', expires_at=expires_at)
