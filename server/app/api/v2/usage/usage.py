from typing import Annotated

from fastapi import Query

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.usage import (
    UsageByEndpoint,
    UsageByMethod,
    UsageByNetwork,
    UsageByRoute,
    UsageEndpointParams,
    UsageFilterParams,
    UsageMethodParams,
    UsageNetworkParams,
    UsageRouteParams,
    UsageSeries,
    UsageSummaryParams,
    UsageWindow,
)
from app.services.usage import GatewayUsageQueryManager

router = BaseRouter(prefix='/usage', route_class=DashRouter)


@router.get('/routes', response_model=UsageByRoute)
async def get_usage_routes(account: AccountIdentityDep, params: Annotated[UsageRouteParams, Query()]) -> UsageByRoute:
    """Return routes ranked by routed request volume with request and retry series."""
    return await GatewayUsageQueryManager.get_routes(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        limit=params.limit,
    )


@router.get('/endpoints', response_model=UsageByEndpoint)
async def get_usage_endpoints(account: AccountIdentityDep, params: Annotated[UsageEndpointParams, Query()]) -> UsageByEndpoint:
    """Return actual upstream Endpoint attempts for an App, Gateway, or route."""
    return await GatewayUsageQueryManager.get_endpoints(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        route_id=params.route_id,
        limit=params.limit,
    )


@router.get('/summary', response_model=UsageWindow)
async def get_usage_summary(account: AccountIdentityDep, params: Annotated[UsageSummaryParams, Query()]) -> UsageWindow:
    return await GatewayUsageQueryManager.get_summary(
        account.id,
        time_range=params.time_range,
        app_id=params.app_id,
        gateway_id=params.gateway_id,
        chain=params.chain,
        network=params.network,
        compare=params.compare,
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
