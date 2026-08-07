from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.http_api_route import HttpApiRouteItem, ReplaceHttpApiRouteParams
from app.services.http_api_route import HttpApiRouteManager

router = BaseRouter(prefix='/gateways/{gateway_id}', route_class=DashRouter)


@router.get('/http-api-route', response_model=HttpApiRouteItem)
async def get_http_api_route(account: AccountIdentityDep, gateway_id: str) -> HttpApiRouteItem:
    return await HttpApiRouteManager.get(account.id, gateway_id)


@router.put('/http-api-route', response_model=HttpApiRouteItem)
async def replace_http_api_route(
    account: AccountIdentityDep,
    gateway_id: str,
    params: ReplaceHttpApiRouteParams,
) -> HttpApiRouteItem:
    return await HttpApiRouteManager.replace(account.id, account.id, gateway_id, params)
