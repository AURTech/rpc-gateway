from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastlog import log
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError

from app.clients.auth import AurPayProfile, GoogleProfile, fetch_aurpay_profile, fetch_google_profile
from app.core.errors import AuthenticationError, ForbiddenError, RateLimitError
from app.infra.db import in_tx
from app.model.account import AccountRole, AccountStatus
from app.model.account.account import normalize_email
from app.model.auth import AuthIdentity, IdentityType, LoginResult, SetPasswordParams
from app.orm.account.account import Account
from app.orm.auth import Auth, AuthProvider, AuthSession
from app.services.auth.password import PasswordWorker, PasswordWorkLimitError
from app.services.auth.session import (
    IssuedSession,
    OAuthLoginState,
    hash_session_token,
    issue_admin_session,
    issue_user_session,
    split_cookie_value,
)
from app.services.auth.settings import get_auth_settings
from app.util import datetime as datetime_util


@dataclass(frozen=True)
class AuthenticatedLogin:
    result: LoginResult
    session: IssuedSession


@dataclass(slots=True, kw_only=True)
class _LoginValues:
    name: str | None
    avatar_url: str | None
    last_login_at: datetime
    last_login_ip: str | None
    last_login_user_agent: str | None
    first_login_at: datetime | None = None


def _login_update(values: _LoginValues) -> dict[str, object]:
    update: dict[str, object] = {
        'name': values.name,
        'avatar_url': values.avatar_url,
        'last_login_at': values.last_login_at,
        'last_login_ip': values.last_login_ip,
        'last_login_user_agent': values.last_login_user_agent,
    }
    if values.first_login_at is not None:
        update['first_login_at'] = values.first_login_at
    return update


class AuthManager:
    def __init__(self, http_client: httpx.AsyncClient, password_worker: PasswordWorker) -> None:
        self._http_client = http_client
        self._password_worker = password_worker

    @staticmethod
    def build_google_login_url(login_state: OAuthLoginState) -> str:
        """Build the Google OAuth authorization URL.

        Side effects:
            None. The caller must persist `login_state.cookie_value` before redirecting.
        """
        settings = get_auth_settings()
        query = urlencode(
            {
                'client_id': settings.google_client_id,
                'redirect_uri': settings.google_redirect_uri,
                'response_type': 'code',
                'scope': 'openid email profile',
                'access_type': 'offline',
                'prompt': 'select_account',
                'state': login_state.state,
                'code_challenge': login_state.code_challenge,
                'code_challenge_method': 'S256',
            }
        )
        return f'https://accounts.google.com/o/oauth2/v2/auth?{query}'

    @staticmethod
    def build_aurpay_login_url(login_state: OAuthLoginState, prompt: Literal['login', 'select_account'] | None = None) -> str:
        settings = get_auth_settings()
        params = {
            'client_id': settings.aurpay_client_id,
            'redirect_uri': settings.aurpay_redirect_uri,
            'response_type': 'code',
            'scope': 'openid profile email',
            'state': login_state.state,
            'nonce': login_state.nonce,
            'code_challenge': login_state.code_challenge,
            'code_challenge_method': 'S256',
        }
        if prompt is not None:
            params['prompt'] = prompt
        query = urlencode(params)
        return f'{settings.aurpay_issuer}/oauth2/authorize?{query}'

    @staticmethod
    def build_auth_callback_url(error: str | None = None, frontend_auth_callback_url: str | None = None) -> str:
        """Build the frontend auth callback URL.

        Side effects:
            None.
        """
        frontend_url = frontend_auth_callback_url or get_auth_settings().frontend_auth_callback_url
        if not error:
            return frontend_url
        parts = urlsplit(frontend_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query.append(('error', error))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    async def _fetch_google_profile(self, code: str, code_verifier: str) -> GoogleProfile:
        settings = get_auth_settings()
        return await fetch_google_profile(
            self._http_client,
            code,
            code_verifier,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
        )

    async def login_with_google(
        self,
        code: str,
        code_verifier: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        """Authenticate a Google OAuth callback and issue an application session.

        Raises:
            ForbiddenError: Google exchange fails, the Google email is unverified, the local account is missing,
                or the Google identity does not match the account binding.

        Side effects:
            Exchanges the external OAuth code before opening a database transaction. Login then locks the account
            before updating login fields, binding the Google identity, and creating a session.
        """
        try:
            profile = await self._fetch_google_profile(code, code_verifier)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning('Google OAuth exchange failed')
            raise ForbiddenError('Google login failed.') from exc

        email = normalize_email(profile.email)

        if not profile.email_verified:
            log.warning('Google email is not verified')
            raise ForbiddenError('Google email is not verified.')

        if email in get_auth_settings().admin_allowed_emails:
            return await self._login_admin(profile, email, client_ip, user_agent)
        return await self._login_user(profile, email, client_ip, user_agent)

    async def login_with_aurpay(
        self,
        code: str,
        code_verifier: str,
        nonce: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        """Authenticate an AurPay OIDC callback and issue an application session.

        Raises:
            ForbiddenError: token exchange or validation fails, the local account is missing, or the AurPay identity does not
                match the account binding.

        Side effects:
            Exchanges and validates the OIDC tokens before opening a database transaction. Login then locks the account,
            updates login fields, binds the AurPay identity, and creates a session.
        """
        settings = get_auth_settings()
        try:
            profile = await fetch_aurpay_profile(
                self._http_client,
                code,
                code_verifier,
                nonce,
                issuer=settings.aurpay_issuer,
                client_id=settings.aurpay_client_id,
                client_secret=settings.aurpay_client_secret,
                redirect_uri=settings.aurpay_redirect_uri,
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning('AurPay OIDC exchange failed')
            raise ForbiddenError('AurPay login failed.') from exc

        email = normalize_email(profile.email)
        if email in settings.admin_allowed_emails:
            return await self._login_aurpay_admin(profile, email, client_ip, user_agent)
        return await self._login_aurpay_user(profile, email, client_ip, user_agent)

    async def _login_aurpay_admin(
        self,
        profile: AurPayProfile,
        email: str,
        ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        auth = await self._get_aurpay_auth(profile.sub)
        admin = auth.account if auth else await Account.filter(email=email, deleted_at=None).first()
        now = datetime_util.now_utc()
        values = _LoginValues(
            name=profile.name,
            avatar_url=None,
            last_login_at=now,
            last_login_ip=ip,
            last_login_user_agent=user_agent,
        )
        created = False
        if admin is None:
            admin, created = await self._create_aurpay_admin(email, values)
        async with in_tx() as connection:
            locked_admin = await self._lock_admin_account(admin.id, using_db=connection)
            if locked_admin is None or locked_admin.deleted_at or locked_admin.email != email:
                account_id = locked_admin.id if locked_admin is not None else admin.id
                log.warning(f'AurPay identity email mismatch | Account:{account_id}')
                raise ForbiddenError('AurPay account is not allowed.')
            self._check_admin_status(locked_admin)
            await self._check_aurpay_binding(locked_admin.id, profile.sub, using_db=connection)
            await self._update_aurpay_login(locked_admin, values, AccountRole.ADMIN, using_db=connection)
            await self._bind_aurpay_auth(locked_admin.id, profile.sub, using_db=connection)
            session = await issue_admin_session(locked_admin.id, using_db=connection)
            admin = locked_admin
        log.info(f'AurPay admin login succeeded | Admin:{admin.id} | Created:{created}')
        return AuthenticatedLogin(
            result=LoginResult(identity_type=IdentityType.ADMIN, id=admin.id, email=admin.email, expires_at=session.expires_at),
            session=session,
        )

    async def _login_aurpay_user(
        self,
        profile: AurPayProfile,
        email: str,
        ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        now = datetime_util.now_utc()
        values = _LoginValues(
            name=profile.name,
            avatar_url=None,
            last_login_at=now,
            last_login_ip=ip,
            last_login_user_agent=user_agent,
        )
        auth = await self._get_aurpay_auth(profile.sub)
        account = auth.account if auth else await Account.filter(email=email, deleted_at=None).first()
        created = False
        if account is None:
            account, created = await self._create_aurpay_user(email, values)
        async with in_tx() as connection:
            locked_account = await Account.select_for_update(using_db=connection).get_or_none(id=account.id)
            if locked_account is None or locked_account.deleted_at or AccountRole(locked_account.role) is not AccountRole.USER:
                account_id = locked_account.id if locked_account is not None else account.id
                log.warning(f'AurPay identity is not bound to a user account | Account:{account_id}')
                raise ForbiddenError('AurPay account is not allowed.')
            if locked_account.status in {AccountStatus.DISABLED, AccountStatus.ARCHIVED}:
                log.warning(
                    f'Account is not allowed to login | Account:{locked_account.id} | Status:{locked_account.status.value}'
                )
                raise ForbiddenError('Account is not allowed to login.')
            await self._check_aurpay_binding(locked_account.id, profile.sub, using_db=connection)
            first_login = locked_account.first_login_at is None
            values.first_login_at = now if first_login else None
            await self._update_aurpay_login(locked_account, values, AccountRole.USER, using_db=connection)
            await self._bind_aurpay_auth(locked_account.id, profile.sub, using_db=connection)
            session = await issue_user_session(locked_account.id, using_db=connection)
            account = locked_account
        if created or first_login:
            log.bind(send_msg=True).info(f'New user | Account:{account.id} | Login:AurPay')
        else:
            log.info(f'AurPay account login succeeded | Account:{account.id}')
        return AuthenticatedLogin(
            result=LoginResult(
                identity_type=IdentityType.USER, id=account.id, email=account.email, expires_at=session.expires_at
            ),
            session=session,
        )

    async def _login_admin(
        self,
        profile: GoogleProfile,
        email: str,
        ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        auth = await self._get_google_auth(profile.sub)
        admin = auth.account if auth else await Account.filter(email=email, deleted_at=None).first()
        now = datetime_util.now_utc()
        values = _LoginValues(
            name=profile.name,
            avatar_url=profile.avatar_url,
            last_login_at=now,
            last_login_ip=ip,
            last_login_user_agent=user_agent,
        )
        created = False
        if admin is None:
            admin, created = await self._create_admin(email, values)
        async with in_tx() as connection:
            locked_admin = await self._lock_admin_account(admin.id, using_db=connection)
            if locked_admin is None or locked_admin.deleted_at or locked_admin.email != email:
                account_id = locked_admin.id if locked_admin is not None else admin.id
                log.warning(f'Google identity email mismatch | Account:{account_id}')
                raise ForbiddenError('Google account is not allowed.')
            self._check_admin_status(locked_admin)
            bound_auth = await (
                Auth.filter(provider=AuthProvider.GOOGLE, identifier=profile.sub, deleted_at=None).using_db(connection).first()
            )
            if bound_auth is not None and bound_auth.account_id != locked_admin.id:
                log.warning(f'Google identity mismatch | Admin:{locked_admin.id}')
                raise ForbiddenError('Google account is not allowed.')
            existing_auth = await (
                Auth.filter(account_id=locked_admin.id, provider=AuthProvider.GOOGLE, deleted_at=None)
                .using_db(connection)
                .first()
            )
            if existing_auth is not None and existing_auth.identifier != profile.sub:
                log.warning(f'Google identity mismatch | Admin:{admin.id}')
                raise ForbiddenError('Google account is not allowed.')
            await self._update_admin_login(locked_admin, values, using_db=connection)
            await self._bind_admin_google_auth(locked_admin.id, profile.sub, using_db=connection)
            session = await issue_admin_session(locked_admin.id, using_db=connection)
            admin = locked_admin
        log.info(f'Admin login succeeded | Admin:{admin.id} | Created:{created}')
        return AuthenticatedLogin(
            result=LoginResult(identity_type=IdentityType.ADMIN, id=admin.id, email=admin.email, expires_at=session.expires_at),
            session=session,
        )

    async def _login_user(
        self,
        profile: GoogleProfile,
        email: str,
        ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        now = datetime_util.now_utc()
        values = _LoginValues(
            name=profile.name,
            avatar_url=profile.avatar_url,
            last_login_at=now,
            last_login_ip=ip,
            last_login_user_agent=user_agent,
        )
        async with in_tx() as connection:
            auth = await (
                Auth.filter(provider=AuthProvider.GOOGLE, identifier=profile.sub, deleted_at=None).using_db(connection).first()
            )
            if auth is not None:
                account = await Account.select_for_update(using_db=connection).get_or_none(id=auth.account_id)
            else:
                account = await Account.select_for_update(using_db=connection).get_or_none(
                    email=email,
                    role=AccountRole.USER,
                    deleted_at=None,
                )
            if account is None:
                log.warning('Local account not found')
                raise ForbiddenError('Google account is not allowed.')
            if account.deleted_at or AccountRole(account.role) is not AccountRole.USER:
                log.warning(f'Google identity is not bound to a user account | Account:{account.id}')
                raise ForbiddenError('Google account is not allowed.')
            if account.status in {AccountStatus.DISABLED, AccountStatus.ARCHIVED}:
                log.warning(f'Account is not allowed to login | Account:{account.id} | Status:{account.status.value}')
                raise ForbiddenError('Account is not allowed to login.')
            bound_auth = await (
                Auth.filter(provider=AuthProvider.GOOGLE, identifier=profile.sub, deleted_at=None).using_db(connection).first()
            )
            if bound_auth is not None and bound_auth.account_id != account.id:
                log.warning(f'Google identity mismatch | Account:{account.id}')
                raise ForbiddenError('Google account is not allowed.')
            existing_auth = await (
                Auth.filter(account_id=account.id, provider=AuthProvider.GOOGLE, deleted_at=None).using_db(connection).first()
            )
            if existing_auth is not None and existing_auth.identifier != profile.sub:
                log.warning(f'Google identity mismatch | Account:{account.id}')
                raise ForbiddenError('Google account is not allowed.')
            first_login = account.first_login_at is None
            values.first_login_at = now if first_login else None
            await self._update_user_login(
                account,
                values,
                using_db=connection,
            )
            await self._bind_user_google_auth(account.id, profile.sub, using_db=connection)
            session = await issue_user_session(account.id, using_db=connection)
        if first_login:
            log.bind(send_msg=True).info(f'New user | Account:{account.id} | Login:Google')
        else:
            log.info(f'Account login succeeded | Account:{account.id}')
        return AuthenticatedLogin(
            result=LoginResult(
                identity_type=IdentityType.USER, id=account.id, email=account.email, expires_at=session.expires_at
            ),
            session=session,
        )

    async def login_with_password(
        self,
        email: str,
        password: str,
        *,
        client_ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        """Authenticate an email and password and issue an application session.

        Raises:
            AuthenticationError: account is missing, has no password, or the password does not match.
            ForbiddenError: account exists but is not allowed to log in.

        Side effects:
            Verifies the expensive password hash before opening a database transaction. Login then locks the account,
            rechecks the verified hash snapshot and active status, updates login fields, and creates a session.
        """
        normalized = normalize_email(email)
        account = await Account.filter(email=normalized, deleted_at=None).first()
        password_hash = account.password_hash if account is not None else None
        password_matches = await self._verify_password(password, password_hash)
        if account is None or password_hash is None or not password_matches:
            log.warning(f'Password login failed | Email:{normalized}')
            raise AuthenticationError('Invalid email or password.')
        if normalized in get_auth_settings().admin_allowed_emails:
            return await self._login_admin_password(account.id, password_hash, client_ip, user_agent)
        return await self._login_user_password(account.id, password_hash, client_ip, user_agent)

    async def _login_admin_password(
        self,
        account_id: str,
        password_hash: str,
        ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        async with in_tx() as connection:
            account = await self._lock_password_account(account_id, password_hash, using_db=connection)
            self._check_admin_status(account)
            now = datetime_util.now_utc()
            account.role = AccountRole.ADMIN
            account.last_login_at = now
            account.last_login_ip = ip
            account.last_login_user_agent = user_agent
            await account.save(
                using_db=connection,
                update_fields=(
                    'role',
                    'last_login_at',
                    'last_login_ip',
                    'last_login_user_agent',
                    'modified_at',
                ),
            )
            session = await issue_admin_session(account.id, using_db=connection)
        log.info(f'Password admin login succeeded | Admin:{account.id}')
        return AuthenticatedLogin(
            result=LoginResult(
                identity_type=IdentityType.ADMIN, id=account.id, email=account.email, expires_at=session.expires_at
            ),
            session=session,
        )

    async def _login_user_password(
        self,
        account_id: str,
        password_hash: str,
        ip: str | None,
        user_agent: str | None,
    ) -> AuthenticatedLogin:
        async with in_tx() as connection:
            account = await self._lock_password_account(account_id, password_hash, using_db=connection)
            if AccountRole(account.role) is not AccountRole.USER or account.status != AccountStatus.ACTIVE:
                log.warning(f'Account is not allowed to login | Account:{account.id} | Status:{account.status.value}')
                raise ForbiddenError('Account is not allowed to login.')
            now = datetime_util.now_utc()
            first_login = account.first_login_at is None
            if first_login:
                account.first_login_at = now
            account.last_login_at = now
            account.last_login_ip = ip
            account.last_login_user_agent = user_agent
            await account.save(
                using_db=connection,
                update_fields=(
                    'first_login_at',
                    'last_login_at',
                    'last_login_ip',
                    'last_login_user_agent',
                    'modified_at',
                ),
            )
            session = await issue_user_session(account.id, using_db=connection)
        if first_login:
            log.bind(send_msg=True).info(f'New user | Account:{account.id} | Login:Password')
        else:
            log.info(f'Password account login succeeded | Account:{account.id}')
        return AuthenticatedLogin(
            result=LoginResult(
                identity_type=IdentityType.USER, id=account.id, email=account.email, expires_at=session.expires_at
            ),
            session=session,
        )

    async def set_password(
        self,
        identity_id: str,
        params: SetPasswordParams,
        *,
        identity_type: IdentityType,
    ) -> IssuedSession:
        """Set or change the password of the authenticated account.

        Raises:
            AuthenticationError: the account no longer exists.
            ForbiddenError: a password already exists and the supplied old password does not match.

        Side effects:
            Updates the account password hash, revokes existing sessions, and issues a replacement session.
        """
        account = await Account.filter(id=identity_id, deleted_at=None).first()
        if account is None:
            raise AuthenticationError('Authentication required.')
        observed_password_hash = account.password_hash
        has_password = bool(observed_password_hash)
        old_password_matches = bool(params.old_password) and await self._verify_password(
            params.old_password or '', observed_password_hash
        )
        if has_password and not old_password_matches:
            log.warning(f'Password change rejected | Account:{account.id}')
            raise ForbiddenError('Old password is incorrect.')
        password_hash = await self._hash_password(params.new_password)
        revoked_at = datetime_util.now_utc()
        async with in_tx() as connection:
            locked_account = (
                await Account.filter(id=account.id, deleted_at=None).using_db(connection).select_for_update().first()
            )
            if locked_account is None:
                raise AuthenticationError('Authentication required.')
            expected_role = AccountRole.ADMIN if identity_type is IdentityType.ADMIN else AccountRole.USER
            if (
                AccountRole(locked_account.role) is not expected_role
                or locked_account.status != AccountStatus.ACTIVE
                or locked_account.password_hash != observed_password_hash
            ):
                log.warning(f'Password change conflicted | Account:{account.id}')
                raise ForbiddenError('Account changed while setting the password. Retry the request.')
            locked_account.password_hash = password_hash
            await locked_account.save(using_db=connection, update_fields=('password_hash', 'modified_at'))
            revoked_sessions = (
                await AuthSession.filter(account_id=account.id, deleted_at=None, revoked_at=None)
                .using_db(connection)
                .update(revoked_at=revoked_at)
            )
            session = (
                await issue_admin_session(account.id, using_db=connection)
                if identity_type is IdentityType.ADMIN
                else await issue_user_session(account.id, using_db=connection)
            )
        log.info(f'Password set | Account:{account.id} | RevokedSessions:{revoked_sessions}')
        return session

    async def get_auth_identity(self, cookie_value: str | None) -> AuthIdentity:
        """Return the identity represented by a session cookie.

        Raises:
            AuthenticationError: session cookie is missing, invalid, expired, revoked, or no longer allowed.
        """
        if not cookie_value:
            raise AuthenticationError('Authentication required.')
        parsed = split_cookie_value(cookie_value)
        if not parsed:
            raise AuthenticationError('Invalid session.')
        identity_type, token = parsed
        return (
            await self._get_admin_identity(token)
            if identity_type == IdentityType.ADMIN
            else await self._get_account_identity(token)
        )

    async def _get_admin_identity(self, token: str) -> AuthIdentity:
        session = await self._get_session(token)
        if not session or session.revoked_at or session.expires_at <= datetime_util.now_utc():
            raise AuthenticationError('Authentication required.')
        admin = session.account
        if (
            admin.deleted_at
            or AccountRole(admin.role) is not AccountRole.ADMIN
            or admin.status != AccountStatus.ACTIVE
            or admin.email not in get_auth_settings().admin_allowed_emails
        ):
            await session.update_from_dict({'revoked_at': datetime_util.now_utc()}).save()
            log.warning(f'Admin email is not allowed | Admin:{admin.id}')
            raise AuthenticationError('Authentication required.')
        return AuthIdentity(
            identity_type=IdentityType.ADMIN, id=admin.id, email=admin.email, name=admin.name, avatar_url=admin.avatar_url
        )

    async def _get_account_identity(self, token: str) -> AuthIdentity:
        session = await self._get_session(token)
        if not session or session.revoked_at or session.expires_at <= datetime_util.now_utc():
            raise AuthenticationError('Authentication required.')
        account = session.account
        if account.deleted_at or AccountRole(account.role) is not AccountRole.USER or account.status != AccountStatus.ACTIVE:
            await session.update_from_dict({'revoked_at': datetime_util.now_utc()}).save()
            log.warning(f'Account session is invalid | Account:{account.id} | Status:{account.status.value}')
            raise AuthenticationError('Authentication required.')
        return AuthIdentity(
            identity_type=IdentityType.USER,
            id=account.id,
            email=account.email,
            name=account.name,
            avatar_url=account.avatar_url,
        )

    async def get_admin_identity(self, cookie_value: str | None) -> AuthIdentity:
        """Return the identity after checking admin privileges.

        Raises:
            AuthenticationError: session cookie is missing or invalid.
            ForbiddenError: session belongs to a non-admin identity.
        """
        identity = await self.get_auth_identity(cookie_value)
        if identity.identity_type != IdentityType.ADMIN:
            raise ForbiddenError('Admin permission required.')
        return identity

    async def logout(self, cookie_value: str | None) -> None:
        """Revoke the session when a valid session cookie is present.

        Side effects:
            Updates the matching session row's `revoked_at` field.
        """
        parsed = split_cookie_value(cookie_value or '')
        if not parsed:
            return
        identity_type, token = parsed
        session = await AuthSession.filter(token_hash=hash_session_token(token), deleted_at=None).first()
        if session and not session.revoked_at:
            await session.update_from_dict({'revoked_at': datetime_util.now_utc()}).save()
            log.info(f'Session logged out | Identity:{identity_type.value} | Session:{session.id}')

    @staticmethod
    async def _get_session(token: str) -> AuthSession | None:
        return (
            await AuthSession.filter(token_hash=hash_session_token(token), deleted_at=None).prefetch_related('account').first()
        )

    @staticmethod
    async def _create_admin(email: str, values: _LoginValues) -> tuple[Account, bool]:
        """Create an admin candidate, or reload the winner of a concurrent email-unique race."""
        try:
            return (
                await Account.create(
                    email=email,
                    role=AccountRole.ADMIN,
                    status=AccountStatus.ACTIVE,
                    name=values.name,
                    avatar_url=values.avatar_url,
                    last_login_at=values.last_login_at,
                    last_login_ip=values.last_login_ip,
                    last_login_user_agent=values.last_login_user_agent,
                ),
                True,
            )
        except IntegrityError as exc:
            admin = await Account.filter(email=email, deleted_at=None).first()
            if admin is None:
                raise ForbiddenError('Google account is not allowed.') from exc
            return admin, False

    @staticmethod
    async def _create_aurpay_admin(email: str, values: _LoginValues) -> tuple[Account, bool]:
        try:
            return (
                await Account.create(
                    email=email,
                    role=AccountRole.ADMIN,
                    status=AccountStatus.ACTIVE,
                    name=values.name,
                    avatar_url=values.avatar_url,
                    last_login_at=values.last_login_at,
                    last_login_ip=values.last_login_ip,
                    last_login_user_agent=values.last_login_user_agent,
                ),
                True,
            )
        except IntegrityError as exc:
            admin = await Account.filter(email=email, deleted_at=None).first()
            if admin is None:
                raise ForbiddenError('AurPay account is not allowed.') from exc
            return admin, False

    @staticmethod
    async def _create_aurpay_user(email: str, values: _LoginValues) -> tuple[Account, bool]:
        try:
            return (
                await Account.create(
                    email=email,
                    role=AccountRole.USER,
                    status=AccountStatus.ACTIVE,
                    name=values.name,
                    avatar_url=values.avatar_url,
                    last_login_at=values.last_login_at,
                    last_login_ip=values.last_login_ip,
                    last_login_user_agent=values.last_login_user_agent,
                ),
                True,
            )
        except IntegrityError as exc:
            account = await Account.filter(email=email, deleted_at=None).first()
            if account is None:
                raise ForbiddenError('AurPay account is not allowed.') from exc
            return account, False

    @staticmethod
    async def _lock_admin_account(
        account_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> Account | None:
        return await Account.select_for_update(using_db=using_db).get_or_none(id=account_id)

    @staticmethod
    async def _update_admin_login(
        account: Account,
        values: _LoginValues,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        update = _login_update(values)
        update['role'] = AccountRole.ADMIN
        try:
            updated = await Account.filter(id=account.id, deleted_at=None).using_db(using_db).update(**update)
        except IntegrityError as exc:
            raise ForbiddenError('Google account is not allowed.') from exc
        if not updated:
            raise ForbiddenError('Google account is not allowed.')
        account.update_from_dict(update)

    @staticmethod
    async def _get_google_auth(google_sub: str) -> Auth | None:
        return (
            await Auth.filter(provider=AuthProvider.GOOGLE, identifier=google_sub, deleted_at=None)
            .prefetch_related('account')
            .first()
        )

    @staticmethod
    async def _get_aurpay_auth(aurpay_sub: str) -> Auth | None:
        return (
            await Auth.filter(provider=AuthProvider.AURPAY, identifier=aurpay_sub, deleted_at=None)
            .prefetch_related('account')
            .first()
        )

    @staticmethod
    async def _check_aurpay_binding(
        account_id: str,
        aurpay_sub: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        bound_auth = await (
            Auth.filter(provider=AuthProvider.AURPAY, identifier=aurpay_sub, deleted_at=None).using_db(using_db).first()
        )
        if bound_auth is not None and bound_auth.account_id != account_id:
            log.warning(f'AurPay identity mismatch | Account:{account_id}')
            raise ForbiddenError('AurPay account is not allowed.')
        existing_auth = await (
            Auth.filter(account_id=account_id, provider=AuthProvider.AURPAY, deleted_at=None).using_db(using_db).first()
        )
        if existing_auth is not None and existing_auth.identifier != aurpay_sub:
            log.warning(f'AurPay identity mismatch | Account:{account_id}')
            raise ForbiddenError('AurPay account is not allowed.')

    @staticmethod
    async def _update_aurpay_login(
        account: Account,
        values: _LoginValues,
        role: AccountRole,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        update = _login_update(values)
        update['role'] = role
        try:
            updated = await Account.filter(id=account.id, deleted_at=None).using_db(using_db).update(**update)
        except IntegrityError as exc:
            raise ForbiddenError('AurPay account is not allowed.') from exc
        if not updated:
            raise ForbiddenError('AurPay account is not allowed.')
        account.update_from_dict(update)

    @staticmethod
    async def _bind_aurpay_auth(
        account_id: str,
        aurpay_sub: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        existing_auth = await (
            Auth.filter(account_id=account_id, provider=AuthProvider.AURPAY, deleted_at=None).using_db(using_db).first()
        )
        if existing_auth is not None:
            if existing_auth.identifier != aurpay_sub:
                raise ForbiddenError('AurPay account is not allowed.')
            return
        try:
            await Auth.create(
                using_db=using_db,
                account_id=account_id,
                provider=AuthProvider.AURPAY,
                identifier=aurpay_sub,
            )
        except IntegrityError as exc:
            raise ForbiddenError('AurPay account is not allowed.') from exc

    @staticmethod
    async def _bind_admin_google_auth(
        account_id: str,
        google_sub: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        existing_auth = await (
            Auth.filter(account_id=account_id, provider=AuthProvider.GOOGLE, deleted_at=None).using_db(using_db).first()
        )
        if existing_auth is not None:
            if existing_auth.identifier != google_sub:
                raise ForbiddenError('Google account is not allowed.')
            return
        try:
            await Auth.create(
                using_db=using_db,
                account_id=account_id,
                provider=AuthProvider.GOOGLE,
                identifier=google_sub,
            )
        except IntegrityError as exc:
            raise ForbiddenError('Google account is not allowed.') from exc

    @staticmethod
    async def _update_user_login(
        account: Account,
        values: _LoginValues,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        update = _login_update(values)
        update['role'] = AccountRole.USER
        try:
            updated = await Account.filter(id=account.id, deleted_at=None).using_db(using_db).update(**update)
        except IntegrityError as exc:
            raise ForbiddenError('Google account is not allowed.') from exc
        if not updated:
            raise ForbiddenError('Google account is not allowed.')
        account.update_from_dict(update)

    @staticmethod
    async def _bind_user_google_auth(
        account_id: str,
        google_sub: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        existing_auth = await (
            Auth.filter(account_id=account_id, provider=AuthProvider.GOOGLE, deleted_at=None).using_db(using_db).first()
        )
        if existing_auth is not None:
            if existing_auth.identifier != google_sub:
                raise ForbiddenError('Google account is not allowed.')
            return
        try:
            await Auth.create(
                using_db=using_db,
                account_id=account_id,
                provider=AuthProvider.GOOGLE,
                identifier=google_sub,
            )
        except IntegrityError as exc:
            raise ForbiddenError('Google account is not allowed.') from exc

    @staticmethod
    async def _lock_password_account(
        account_id: str,
        password_hash: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> Account:
        """Lock the account and reject a password snapshot invalidated during Argon2 verification."""
        account = await Account.select_for_update(using_db=using_db).get_or_none(id=account_id, deleted_at=None)
        if account is None or account.password_hash != password_hash:
            log.warning(f'Password login conflicted | Account:{account_id}')
            raise AuthenticationError('Invalid email or password.')
        return account

    @staticmethod
    def _check_admin_status(account: Account) -> None:
        if account.status in {AccountStatus.DISABLED, AccountStatus.ARCHIVED}:
            log.warning(f'Admin is not allowed to login | Admin:{account.id} | Status:{account.status.value}')
            raise ForbiddenError('Account is not allowed to login.')

    async def _verify_password(self, raw: str, stored: str | None) -> bool:
        try:
            return await self._password_worker.verify(raw, stored)
        except PasswordWorkLimitError as exc:
            log.warning('Password worker capacity is exhausted')
            raise RateLimitError() from exc

    async def _hash_password(self, raw: str) -> str:
        try:
            return await self._password_worker.hash(raw)
        except PasswordWorkLimitError as exc:
            log.warning('Password worker capacity is exhausted')
            raise RateLimitError() from exc
