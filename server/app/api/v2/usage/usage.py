from typing import Annotated

from fastapi import Query

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.usage import (
    UsageByMethod,
    UsageByNetwork,
    UsageFilterParams,
    UsageMethodParams,
    UsageNetworkParams,
    UsageSeries,
    UsageWindow,
)
from app.services.usage import GatewayUsageQueryManager

router = BaseRouter(prefix='/usage', route_class=DashRouter)


@router.get('/summary', response_model=UsageWindow)
async def get_usage_summary(account: AccountIdentityDep, params: Annotated[UsageFilterParams, Query()]) -> UsageWindow:
    return await GatewayUsageQueryManager.get_summary(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        chain=params.chain,
        network=params.network,
    )


@router.get('/series', response_model=UsageSeries)
async def get_usage_series(account: AccountIdentityDep, params: Annotated[UsageFilterParams, Query()]) -> UsageSeries:
    return await GatewayUsageQueryManager.get_series(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        chain=params.chain,
        network=params.network,
    )


@router.get('/methods', response_model=UsageByMethod)
async def get_usage_methods(account: AccountIdentityDep, params: Annotated[UsageMethodParams, Query()]) -> UsageByMethod:
    """Return method series ranked by request volume or cache-eligible request volume."""
    return await GatewayUsageQueryManager.get_methods(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        chain=params.chain,
        network=params.network,
        rank_by=params.rank_by,
        limit=params.limit,
    )


@router.get('/networks', response_model=UsageByNetwork)
async def get_usage_networks(account: AccountIdentityDep, params: Annotated[UsageNetworkParams, Query()]) -> UsageByNetwork:
    return await GatewayUsageQueryManager.get_networks(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        chain=params.chain,
        network=params.network,
        limit=params.limit,
    )
