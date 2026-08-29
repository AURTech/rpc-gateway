from typing import Annotated

from fastapi import Query, Response, status
from jobs.provider.provider import run_provider_sync

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep, ProviderManagerDep, SessionIdentityDep
from app.core.private_cache import apply_private_cache
from app.model.auth import PersonalAccessTokenScope
from app.model.provider import (
    CreateProviderParams,
    ProviderCredentialDetail,
    ProviderDeleteImpact,
    ProviderDeleteParams,
    ProviderDeleteResult,
    ProviderEndpointList,
    ProviderEndpointListParams,
    ProviderItem,
    ProviderList,
    ProviderListParams,
    ProviderSyncRunItem,
    ProviderSyncRunList,
    ProviderSyncRunListParams,
    ProviderSyncTrigger,
    UpdateProviderParams,
)

router = BaseRouter(prefix='/providers', route_class=DashRouter)


@router.post('', response_model=ProviderItem, status_code=status.HTTP_201_CREATED)
async def create_provider(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    params: CreateProviderParams,
) -> ProviderItem:
    """Create an account-owned Provider with an encrypted credential."""
    value = await provider_manager.create_provider(account.id, params)
    apply_private_cache(response.headers)
    return value


@router.get('', response_model=ProviderList)
async def list_providers(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    params: Annotated[ProviderListParams, Query()],
) -> ProviderList:
    return await provider_manager.list_providers(
        account.id,
        q=params.q,
        vendor=params.vendor,
        enabled=params.enabled,
        sync_enabled=params.sync_enabled,
        last_sync_status=params.last_sync_status,
        page=params.page,
        size=params.size,
    )


@router.get('/{provider_id}', response_model=ProviderItem)
async def get_provider(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
) -> ProviderItem:
    value = await provider_manager.get_provider(account.id, provider_id)
    apply_private_cache(response.headers)
    return value


@router.get('/{provider_id}/credential', response_model=ProviderCredentialDetail)
async def get_provider_credential(
    response: Response,
    account: SessionIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
) -> ProviderCredentialDetail:
    value = await provider_manager.get_credential(account.id, provider_id)
    apply_private_cache(response.headers)
    return value


@router.patch('/{provider_id}', response_model=ProviderItem)
async def update_provider(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
    params: UpdateProviderParams,
) -> ProviderItem:
    value = await provider_manager.update_provider(account.id, provider_id, params)
    apply_private_cache(response.headers)
    return value


@router.delete('/{provider_id}', response_model=ProviderDeleteResult)
async def delete_provider(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
    params: Annotated[ProviderDeleteParams, Query()],
) -> ProviderDeleteResult:
    """Soft-delete a Provider, detach its Endpoints, and optionally archive unreferenced Endpoints."""
    return await provider_manager.delete_provider(
        account.id,
        provider_id,
        delete_unreferenced_endpoints=params.delete_unreferenced_endpoints,
    )


@router.get('/{provider_id}/delete-impact', response_model=ProviderDeleteImpact)
async def get_delete_impact(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
) -> ProviderDeleteImpact:
    return await provider_manager.get_delete_impact(account.id, provider_id)


@router.post('/{provider_id}/sync', response_model=ProviderSyncRunItem, status_code=status.HTTP_202_ACCEPTED)
async def sync_provider(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
) -> ProviderSyncRunItem:
    """Queue Provider discovery and return its persistent run."""
    run, created = await provider_manager.create_sync_run(account.id, provider_id, trigger=ProviderSyncTrigger.MANUAL)
    if created:
        await run_provider_sync.kiq(run.id)
    return run


@router.get('/{provider_id}/sync-runs', response_model=ProviderSyncRunList)
async def list_sync_runs(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
    params: Annotated[ProviderSyncRunListParams, Query()],
) -> ProviderSyncRunList:
    return await provider_manager.list_sync_runs(account.id, provider_id, page=params.page, size=params.size)


@router.get('/{provider_id}/sync-runs/{run_id}', response_model=ProviderSyncRunItem)
async def get_sync_run(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
    run_id: str,
) -> ProviderSyncRunItem:
    return await provider_manager.get_sync_run(account.id, provider_id, run_id)


@router.get('/{provider_id}/endpoints', response_model=ProviderEndpointList)
async def list_provider_endpoints(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
    params: Annotated[ProviderEndpointListParams, Query()],
) -> ProviderEndpointList:
    """List active and archived Endpoints managed by one Provider."""
    value = await provider_manager.list_provider_endpoints(
        account.id,
        provider_id,
        include_effective_url=(not account.uses_pat or PersonalAccessTokenScope.ENDPOINT_SECRETS_READ in account.pat_scopes),
        discovery_status=params.discovery_status,
        q=params.q,
        chain=params.chain,
        network=params.network,
        protocol=params.protocol,
        retained_by_routes=params.retained_by_routes,
        page=params.page,
        size=params.size,
    )
    apply_private_cache(response.headers)
    return value
