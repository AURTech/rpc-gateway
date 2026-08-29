import pytest
from app.core.errors import BadRequestError
from app.model.provider import ProviderSyncRunState, ProviderSyncTrigger, ProviderVendor
from app.orm.account import Account
from app.orm.provider import Provider, ProviderSyncRun
from app.services.provider import ProviderManager
from app.services.provider.crypto import encrypt_provider_credential
from fastapi import FastAPI


@pytest.mark.anyio
async def test_provider_sync_run_is_persistent_and_deduplicated(app: FastAPI) -> None:
    account = await Account.create(email='provider-run@example.com')
    provider = await Provider.create(
        account_id=account.id,
        name='Run provider',
        vendor=ProviderVendor.ALCHEMY,
        enabled=True,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    first, created = await manager.create_sync_run(
        account.id,
        provider.id,
        trigger=ProviderSyncTrigger.MANUAL,
    )
    repeated, repeated_created = await manager.create_sync_run(
        account.id,
        provider.id,
        trigger=ProviderSyncTrigger.MANUAL,
    )

    assert created is True
    assert repeated_created is False
    assert repeated.id == first.id
    assert first.state == ProviderSyncRunState.QUEUED

    listing = await manager.list_sync_runs(account.id, provider.id, page=1, size=20)
    detail = await manager.get_sync_run(account.id, provider.id, first.id)

    assert listing.total == 1
    assert listing.items[0].id == first.id
    assert detail.id == first.id
    assert detail.endpoint_changes == 0

    await ProviderSyncRun.filter(id=first.id).update(state=ProviderSyncRunState.SUCCESS, created=2, updated=1)
    completed = await manager.get_sync_run(account.id, provider.id, first.id)
    assert completed.endpoint_changes == 3
    next_run, next_created = await manager.create_sync_run(
        account.id,
        provider.id,
        trigger=ProviderSyncTrigger.SCHEDULED,
    )
    assert next_created is True
    assert next_run.id != first.id


@pytest.mark.anyio
async def test_paused_provider_rejects_new_sync_run(app: FastAPI) -> None:
    account = await Account.create(email='provider-paused-run@example.com')
    provider = await Provider.create(
        account_id=account.id,
        name='Paused provider',
        vendor=ProviderVendor.ALCHEMY,
        enabled=False,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    with pytest.raises(BadRequestError, match='Provider is disabled'):
        await manager.create_sync_run(
            account.id,
            provider.id,
            trigger=ProviderSyncTrigger.MANUAL,
        )
