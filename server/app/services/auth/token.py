import hashlib
import hmac
import secrets
from datetime import timedelta

from fastlog import log
from tortoise.expressions import Q

from app.core.config import CONF
from app.core.errors import AuthenticationError, BadRequestError, ConflictError, ForbiddenError, NotfoundError
from app.infra.db import in_tx
from app.model.account import AccountRole, AccountStatus
from app.model.auth import (
    ADMIN_PAT_SCOPES,
    AuthIdentity,
    CreatedPersonalAccessToken,
    CreatePersonalAccessTokenParams,
    IdentityType,
    PersonalAccessTokenItem,
    PersonalAccessTokenList,
    PersonalAccessTokenScope,
    PersonalAccessTokenState,
    RevokedPersonalAccessToken,
)
from app.orm.account import Account
from app.orm.auth import PersonalAccessToken
from app.services.auth.settings import get_auth_settings
from app.util import datetime as datetime_util

PAT_PREFIX = 'rg_pat_'
PAT_DEFAULT_TTL_DAYS = 90
PAT_MAX_TTL_DAYS = 365
PAT_LAST_USED_WRITE_SECONDS = 300
PAT_SECRET_BYTES = 32
PAT_DISPLAY_LENGTH = 14
PAT_MAX_ACTIVE_TOKENS = 20


def hash_pat(token: str) -> str:
    secret = CONF.AUTH_PAT_HASH_SECRET.strip().encode()
    if not secret:
        raise RuntimeError('AUTH_PAT_HASH_SECRET is not configured.')
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def _token_state(token: PersonalAccessToken) -> PersonalAccessTokenState:
    if token.revoked_at is not None:
        return PersonalAccessTokenState.REVOKED
    if token.expires_at <= datetime_util.now_utc():
        return PersonalAccessTokenState.EXPIRED
    return PersonalAccessTokenState.ACTIVE


def _scopes(token: PersonalAccessToken) -> list[PersonalAccessTokenScope]:
    try:
        return [PersonalAccessTokenScope(value) for value in token.scopes]
    except (TypeError, ValueError) as exc:
        raise AuthenticationError('Invalid personal access token.', code='auth.invalid_token') from exc


class PersonalAccessTokenManager:
    @staticmethod
    async def create(
        identity: AuthIdentity,
        params: CreatePersonalAccessTokenParams,
    ) -> CreatedPersonalAccessToken:
        now = datetime_util.now_utc()
        expires_at = params.expires_at or now + timedelta(days=PAT_DEFAULT_TTL_DAYS)
        max_expires_at = now + timedelta(days=PAT_MAX_TTL_DAYS)
        if expires_at <= now:
            raise BadRequestError('Personal access token expiry must be in the future.')
        if expires_at > max_expires_at:
            raise BadRequestError('Personal access token expiry cannot exceed 365 days.')

        scopes = set(params.scopes)
        if scopes & ADMIN_PAT_SCOPES and identity.identity_type is not IdentityType.ADMIN:
            raise ForbiddenError('Admin personal access token scopes require an admin account.')

        raw_token = f'{PAT_PREFIX}{secrets.token_urlsafe(PAT_SECRET_BYTES)}'
        async with in_tx() as connection:
            await Account.select_for_update(using_db=connection).get(id=identity.id, deleted_at=None)
            active = await (
                PersonalAccessToken.filter(
                    account_id=identity.id,
                    deleted_at=None,
                    revoked_at=None,
                    expires_at__gt=now,
                )
                .using_db(connection)
                .count()
            )
            if active >= PAT_MAX_ACTIVE_TOKENS:
                raise ConflictError(
                    f'An account can have at most {PAT_MAX_ACTIVE_TOKENS} active personal access tokens.',
                    code='personal_access_tokens.limit_reached',
                    details={'active': active, 'max_active': PAT_MAX_ACTIVE_TOKENS},
                )
            token = await PersonalAccessToken.create(
                using_db=connection,
                account_id=identity.id,
                name=params.name,
                token_digest=hash_pat(raw_token),
                token_prefix=raw_token[:PAT_DISPLAY_LENGTH],
                scopes=[scope.value for scope in params.scopes],
                expires_at=expires_at,
            )
        log.info(f'Personal access token created | Account:{identity.id} | Token:{token.id}')
        item = PersonalAccessTokenManager.to_item(token)
        return CreatedPersonalAccessToken(**item.model_dump(), token=raw_token)

    @staticmethod
    async def list(
        account_id: str,
        *,
        page: int,
        size: int,
        state: PersonalAccessTokenState | None,
    ) -> PersonalAccessTokenList:
        now = datetime_util.now_utc()
        query = PersonalAccessToken.filter(account_id=account_id, deleted_at=None)
        if state is PersonalAccessTokenState.ACTIVE:
            query = query.filter(revoked_at=None, expires_at__gt=now)
        elif state is PersonalAccessTokenState.EXPIRED:
            query = query.filter(revoked_at=None, expires_at__lte=now)
        elif state is PersonalAccessTokenState.REVOKED:
            query = query.filter(revoked_at__isnull=False)

        total = await query.count()
        active = await PersonalAccessToken.filter(
            account_id=account_id,
            deleted_at=None,
            revoked_at=None,
            expires_at__gt=now,
        ).count()
        rows = await query.order_by('-created_at').offset((page - 1) * size).limit(size)
        max_page = (total + size - 1) // size if total else 0
        return PersonalAccessTokenList(
            page=page,
            size=size,
            total=total,
            max_page=max_page,
            active=active,
            max_active=PAT_MAX_ACTIVE_TOKENS,
            items=[PersonalAccessTokenManager.to_item(row) for row in rows],
        )

    @staticmethod
    async def revoke(account_id: str, token_id: str) -> RevokedPersonalAccessToken:
        token = await PersonalAccessToken.filter(id=token_id, account_id=account_id, deleted_at=None).first()
        if token is None:
            raise NotfoundError('Personal access token not found.')
        revoked_at = token.revoked_at or datetime_util.now_utc()
        if token.revoked_at is None:
            token.revoked_at = revoked_at
            await token.save(update_fields=('revoked_at', 'modified_at'))
            log.info(f'Personal access token revoked | Account:{account_id} | Token:{token.id}')
        return RevokedPersonalAccessToken(id=token.id, revoked=True, revoked_at=revoked_at)

    @staticmethod
    async def authenticate(raw_token: str) -> AuthIdentity:
        if not raw_token.startswith(PAT_PREFIX) or len(raw_token) > 128:
            raise AuthenticationError('Invalid personal access token.', code='auth.invalid_token')
        try:
            digest = hash_pat(raw_token)
        except RuntimeError as exc:
            log.error('Personal access token authentication is unavailable')
            raise AuthenticationError('Personal access token authentication is unavailable.') from exc
        token = await PersonalAccessToken.filter(token_digest=digest, deleted_at=None).prefetch_related('account').first()
        if token is None or not hmac.compare_digest(token.token_digest, digest):
            raise AuthenticationError('Invalid personal access token.', code='auth.invalid_token')
        if token.revoked_at is not None:
            raise AuthenticationError('Personal access token is revoked.', code='auth.token_revoked')
        now = datetime_util.now_utc()
        if token.expires_at <= now:
            raise AuthenticationError('Personal access token is expired.', code='auth.token_expired')

        account = token.account
        role = AccountRole(account.role)
        allowed_admins = get_auth_settings().admin_allowed_emails
        valid_admin = role is AccountRole.ADMIN and account.email in allowed_admins
        valid_user = role is AccountRole.USER
        if account.deleted_at or account.status != AccountStatus.ACTIVE or not (valid_admin or valid_user):
            raise AuthenticationError('Authentication required.', code='auth.invalid_token')

        stale_before = now - timedelta(seconds=PAT_LAST_USED_WRITE_SECONDS)
        if token.last_used_at is None or token.last_used_at <= stale_before:
            await (
                PersonalAccessToken.filter(id=token.id, deleted_at=None)
                .filter(Q(last_used_at=None) | Q(last_used_at__lte=stale_before))
                .update(last_used_at=now)
            )

        identity_type = IdentityType.ADMIN if valid_admin else IdentityType.USER
        return AuthIdentity(
            identity_type=identity_type,
            id=account.id,
            email=account.email,
            name=account.name,
            avatar_url=account.avatar_url,
            pat_id=token.id,
            pat_scopes=frozenset(_scopes(token)),
        )

    @staticmethod
    def to_item(token: PersonalAccessToken) -> PersonalAccessTokenItem:
        return PersonalAccessTokenItem(
            id=token.id,
            name=token.name,
            token_prefix=token.token_prefix,
            scopes=_scopes(token),
            state=_token_state(token),
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
            revoked_at=token.revoked_at,
            created_at=token.created_at,
        )
