from typing import Annotated

from fastapi import Query, Response, status

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.core.private_cache import apply_private_cache
from app.model.application import (
    AppItem,
    AppKeyItem,
    AppKeyList,
    AppList,
    AppListParams,
    AppProviderResult,
    CreateAppParams,
    CreatedApp,
    CreatedAppKey,
    DeletedApp,
    SetAppProviderParams,
    UpdateAppParams,
)
from app.model.gateway import BulkUpdateGatewayParams, BulkUpdateGatewayResult
from app.services.application import ApplicationManager, AppProviderManager
from app.services.gateway import GatewayManager

router = BaseRouter(prefix='/apps', route_class=DashRouter)


@router.post('', response_model=CreatedApp, status_code=status.HTTP_201_CREATED)
async def create_app(response: Response, account: AccountIdentityDep, params: CreateAppParams) -> CreatedApp:
    """Create an App, its first API Key, and its catalog snapshot of Gateways."""
    value = await ApplicationManager.create_app(account.id, account.id, params)
    apply_private_cache(response.headers)
    return value


@router.get('', response_model=AppList)
async def list_apps(account: AccountIdentityDep, params: Annotated[AppListParams, Query()]) -> AppList:
    return await ApplicationManager.list_apps(
        account.id,
        search=params.search,
        enabled=params.enabled,
        start_at=params.start_at,
        end_at=params.end_at,
        sort=params.sort,
        page=params.page,
        size=params.size,
    )


@router.get('/{app_id}/api-keys', response_model=AppKeyList)
async def list_api_keys(response: Response, account: AccountIdentityDep, app_id: str) -> AppKeyList:
    value = await ApplicationManager.list_keys(account.id, app_id)
    apply_private_cache(response.headers)
    return value


@router.post('/{app_id}/api-keys/rotate', response_model=CreatedAppKey, status_code=status.HTTP_201_CREATED)
async def rotate_api_key(response: Response, account: AccountIdentityDep, app_id: str) -> CreatedAppKey:
    """Create an API Key and move the prior active Key into its configured grace period."""
    value = await ApplicationManager.rotate_key(account.id, account.id, app_id)
    apply_private_cache(response.headers)
    return value


@router.post('/{app_id}/api-keys/{key_id}/revoke', response_model=AppKeyItem)
async def revoke_api_key(response: Response, account: AccountIdentityDep, app_id: str, key_id: str) -> AppKeyItem:
    value = await ApplicationManager.revoke_key(account.id, account.id, app_id, key_id)
    apply_private_cache(response.headers)
    return value


@router.patch('/{app_id}/gateways', response_model=BulkUpdateGatewayResult)
async def bulk_update_app_gateways(
    account: AccountIdentityDep,
    app_id: str,
    params: BulkUpdateGatewayParams,
) -> BulkUpdateGatewayResult:
    """Atomically set enabled for Gateways belonging to one App using optimistic versions."""
    return await GatewayManager.bulk_update_gateways(account.id, account.id, app_id, params)


@router.put('/{app_id}/provider', response_model=AppProviderResult)
async def set_app_provider(
    account: AccountIdentityDep,
    app_id: str,
    params: SetAppProviderParams,
) -> AppProviderResult:
    """Associate an enabled account Provider and publish its matching Endpoints to this App."""
    return await AppProviderManager.set_provider(account.id, app_id, params.provider_id)


@router.delete('/{app_id}/provider', response_model=AppProviderResult)
async def clear_app_provider(account: AccountIdentityDep, app_id: str) -> AppProviderResult:
    """Remove the Provider association and its automatically managed Route Targets."""
    return await AppProviderManager.clear_provider(account.id, app_id)


@router.get('/{app_id}', response_model=AppItem)
async def get_app(account: AccountIdentityDep, app_id: str) -> AppItem:
    return await ApplicationManager.get_app(account.id, app_id)


@router.patch('/{app_id}', response_model=AppItem)
async def update_app(account: AccountIdentityDep, app_id: str, params: UpdateAppParams) -> AppItem:
    return await ApplicationManager.update_app(account.id, account.id, app_id, params)


@router.delete('/{app_id}', response_model=DeletedApp)
async def delete_app(account: AccountIdentityDep, app_id: str) -> DeletedApp:
    return await ApplicationManager.delete_app(account.id, account.id, app_id)
