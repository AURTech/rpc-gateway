from typing import Annotated

from fastapi import Query

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.gateway import GatewayItem, GatewayList, GatewayListParams, UpdateGatewayParams
from app.services.gateway import GatewayManager

router = BaseRouter(prefix='/gateways', route_class=DashRouter)


@router.get('', response_model=GatewayList)
async def list_gateways(account: AccountIdentityDep, params: Annotated[GatewayListParams, Query()]) -> GatewayList:
    return await GatewayManager.list_gateways(
        account.id,
        app_id=params.app_id,
        chain=params.chain,
        network=params.network,
        enabled=params.enabled,
        search=params.search,
        start_at=params.start_at,
        end_at=params.end_at,
        sort=params.sort,
        page=params.page,
        size=params.size,
    )


@router.get('/{gateway_id}', response_model=GatewayItem)
async def get_gateway(account: AccountIdentityDep, gateway_id: str) -> GatewayItem:
    return await GatewayManager.get_gateway(account.id, gateway_id)


@router.patch('/{gateway_id}', response_model=GatewayItem)
async def update_gateway(
    account: AccountIdentityDep,
    gateway_id: str,
    params: UpdateGatewayParams,
) -> GatewayItem:
    return await GatewayManager.update_gateway(account.id, account.id, gateway_id, params)
