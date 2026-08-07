from typing import Annotated

from fastapi import Query, Response, status

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep, ProviderManagerDep
from app.core.private_cache import apply_private_cache
from app.model.auth import PersonalAccessTokenScope
from app.model.provider import (
    CreateProviderParams,
    ProviderDeleteParams,
    ProviderDeleteResult,
    ProviderDetail,
    ProviderEndpointList,
    ProviderEndpointListParams,
    ProviderItem,
    ProviderList,
    ProviderListParams,
    ProviderSyncResult,
    UpdateProviderParams,
    redact_provider_detail,
)

router = BaseRouter(prefix='/providers', route_class=DashRouter)


@router.post('', response_model=ProviderDetail | ProviderItem, status_code=status.HTTP_201_CREATED)
async def create_provider(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    params: CreateProviderParams,
) -> ProviderDetail | ProviderItem:
    """Create an account-owned Provider with an encrypted credential."""
    value = await provider_manager.create_provider(account.id, params)
    apply_private_cache(response.headers)
    if account.uses_pat and PersonalAccessTokenScope.PROVIDER_SECRETS_READ not in account.pat_scopes:
        return redact_provider_detail(value)
    return value


@router.get('', response_model=ProviderList)
async def list_providers(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    params: Annotated[ProviderListParams, Query()],
) -> ProviderList:
    return await provider_manager.list_providers(
        account.id,
        vendor=params.vendor,
        enabled=params.enabled,
        sync_enabled=params.sync_enabled,
        page=params.page,
        size=params.size,
    )


@router.get('/{provider_id}', response_model=ProviderDetail | ProviderItem)
async def get_provider(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
) -> ProviderDetail | ProviderItem:
    value = await provider_manager.get_provider(account.id, provider_id)
    apply_private_cache(response.headers)
    if account.uses_pat and PersonalAccessTokenScope.PROVIDER_SECRETS_READ not in account.pat_scopes:
        return redact_provider_detail(value)
    return value


@router.patch('/{provider_id}', response_model=ProviderDetail | ProviderItem)
async def update_provider(
    response: Response,
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
    params: UpdateProviderParams,
) -> ProviderDetail | ProviderItem:
    value = await provider_manager.update_provider(account.id, provider_id, params)
    apply_private_cache(response.headers)
    if account.uses_pat and PersonalAccessTokenScope.PROVIDER_SECRETS_READ not in account.pat_scopes:
        return redact_provider_detail(value)
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


@router.post('/{provider_id}/sync', response_model=ProviderSyncResult)
async def sync_provider(
    account: AccountIdentityDep,
    provider_manager: ProviderManagerDep,
    provider_id: str,
) -> ProviderSyncResult:
    """Discover and transactionally publish the Provider Endpoint inventory."""
    return await provider_manager.sync_provider(account.id, provider_id)


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
        sync_status=params.sync_status,
        page=params.page,
        size=params.size,
    )
    apply_private_cache(response.headers)
    return value
