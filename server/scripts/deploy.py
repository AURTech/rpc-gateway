#!/usr/bin/env python3
"""Create standard developer accounts for a deployment.

The script is idempotent. Existing accounts are left unchanged. Production
passwords are generated at creation time and printed once. Dev/test passwords
are fixed so local environments can be rebuilt consistently.
"""

import asyncio
import secrets
import sys
from dataclasses import dataclass

from app.core.config import CONF, Config
from app.infra.db import TORTOISE_ORM
from app.model.account import AccountRole, AccountStatus
from app.model.account.account import normalize_email
from app.orm.account.account import Account
from app.services.auth.password import hash_password
from app.services.auth.settings import get_auth_settings
from tortoise import Tortoise

_PROD_PASSWORD_BYTES = 24

DEV_ACCOUNT_PASSWORDS = {
    'admin@example.test': 'tiTjpKS46zN8RnpAaulIOsW2',
    'u1@example.test': 'vUByYtF1nH8czcIDwOr8mw4t',
    'u2@example.test': 'l6Vi_YlWBS4ok3EN1sa3nKlU',
}


@dataclass(frozen=True, slots=True, kw_only=True)
class _DeveloperAccount:
    email: str
    role: AccountRole


DEVELOPER_ACCOUNTS = (
    _DeveloperAccount(email='admin@example.test', role=AccountRole.ADMIN),
    _DeveloperAccount(email='u1@example.test', role=AccountRole.USER),
    _DeveloperAccount(email='u2@example.test', role=AccountRole.USER),
)


def _build_password(*, email: str, app_env: str) -> str:
    if app_env == 'prod':
        return secrets.token_urlsafe(_PROD_PASSWORD_BYTES)
    return DEV_ACCOUNT_PASSWORDS[email]


def validate_deploy_settings(conf: Config = CONF) -> None:
    allowed_admins = get_auth_settings(conf).admin_allowed_emails
    deploy_admins = {normalize_email(account.email) for account in DEVELOPER_ACCOUNTS if account.role is AccountRole.ADMIN}
    missing_admins = sorted(deploy_admins - allowed_admins)
    if missing_admins:
        missing = ', '.join(missing_admins)
        raise ValueError(f'ADMIN_ALLOWED_EMAILS must include {missing} before running deploy.')


async def _deploy_one(account: _DeveloperAccount, *, app_env: str) -> str:
    email = normalize_email(account.email)
    if await Account.get_or_none(email=email, deleted_at=None) is not None:
        return f'skipped {email} ({account.role.value})'

    password = _build_password(email=email, app_env=app_env)
    await Account.create(
        email=email,
        role=account.role,
        status=AccountStatus.ACTIVE,
        password_hash=hash_password(password),
    )
    return f'created {email} ({account.role.value}) password={password}'


async def _deploy_accounts(app_env: str) -> list[str]:
    messages: list[str] = []
    for account in DEVELOPER_ACCOUNTS:
        messages.append(await _deploy_one(account, app_env=app_env))
    return messages


async def _run() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        for message in await _deploy_accounts(CONF.APP_ENV):
            print(message)
    finally:
        await Tortoise.close_connections()


def main() -> None:
    try:
        validate_deploy_settings(CONF)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    asyncio.run(_run())


if __name__ == '__main__':
    main()
