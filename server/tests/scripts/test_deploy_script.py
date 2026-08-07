import importlib.util
import sys
import types
from pathlib import Path

import pytest
from app.core.config import Config
from app.model.account import AccountRole, AccountStatus
from app.orm.account.account import Account
from app.services.auth.password import hash_password, verify_password
from fastapi import FastAPI


def _load_script_module() -> types.ModuleType:
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'deploy.py'
    spec = importlib.util.spec_from_file_location('deploy', script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dev_passwords_are_fixed() -> None:
    module = _load_script_module()

    assert (
        module._build_password(email='admin@example.test', app_env='dev') == module.DEV_ACCOUNT_PASSWORDS['admin@example.test']
    )
    assert module._build_password(email='u1@example.test', app_env='test') == module.DEV_ACCOUNT_PASSWORDS['u1@example.test']


def test_prod_passwords_are_random() -> None:
    module = _load_script_module()

    first = module._build_password(email='admin@example.test', app_env='prod')
    second = module._build_password(email='admin@example.test', app_env='prod')

    assert first != second
    assert len(first) >= 24
    assert len(second) >= 24


def test_validate_deploy_settings_requires_admin_allowed_email() -> None:
    module = _load_script_module()
    conf = Config.model_validate({'APP_ENV': 'dev', 'ADMIN_ALLOWED_EMAILS': ['other@example.com']})

    with pytest.raises(ValueError, match='ADMIN_ALLOWED_EMAILS must include admin@example.test'):
        module.validate_deploy_settings(conf)


def test_validate_deploy_settings_accepts_admin_allowed_email() -> None:
    module = _load_script_module()
    conf = Config.model_validate({'APP_ENV': 'dev', 'ADMIN_ALLOWED_EMAILS': ['Admin@Example.TEST']})

    module.validate_deploy_settings(conf)


@pytest.mark.anyio
async def test_deploy_accounts_creates_missing_developer_accounts(app: FastAPI) -> None:
    _ = app
    module = _load_script_module()

    messages = await module._deploy_accounts('dev')

    assert messages == [
        f'created admin@example.test (admin) password={module.DEV_ACCOUNT_PASSWORDS["admin@example.test"]}',
        f'created u1@example.test (user) password={module.DEV_ACCOUNT_PASSWORDS["u1@example.test"]}',
        f'created u2@example.test (user) password={module.DEV_ACCOUNT_PASSWORDS["u2@example.test"]}',
    ]
    accounts = await Account.all().order_by('email')
    assert [(account.email, account.role, account.status) for account in accounts] == [
        ('admin@example.test', AccountRole.ADMIN, AccountStatus.ACTIVE),
        ('u1@example.test', AccountRole.USER, AccountStatus.ACTIVE),
        ('u2@example.test', AccountRole.USER, AccountStatus.ACTIVE),
    ]
    for account in accounts:
        assert account.password_hash is not None
        assert verify_password(module.DEV_ACCOUNT_PASSWORDS[account.email], account.password_hash)


@pytest.mark.anyio
async def test_deploy_accounts_skips_existing_accounts_without_changes(app: FastAPI) -> None:
    _ = app
    module = _load_script_module()
    old_password_hash = hash_password('old-password')
    await Account.create(
        email='u1@example.test',
        role=AccountRole.ADMIN,
        status=AccountStatus.DISABLED,
        password_hash=old_password_hash,
    )

    messages = await module._deploy_accounts('dev')

    assert messages[1] == 'skipped u1@example.test (user)'
    existing = await Account.get(email='u1@example.test')
    assert existing.role == AccountRole.ADMIN
    assert existing.status == AccountStatus.DISABLED
    password_hash = existing.password_hash
    assert password_hash is not None
    assert password_hash == old_password_hash
    assert verify_password('old-password', password_hash)
