from typing import Annotated

from fastapi import Query, status

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.jsonrpc_route import (
    CreateJsonRpcMethodRouteParams,
    DeleteJsonRpcMethodRouteParams,
    JsonRpcMethodRouteList,
    JsonRpcRouteItem,
    ReplaceJsonRpcMethodRouteParams,
    ReplaceJsonRpcRouteParams,
)
from app.services.jsonrpc_route import JsonRpcRouteManager

router = BaseRouter(prefix='/gateways/{gateway_id}', route_class=DashRouter)


@router.get('/jsonrpc-route', response_model=JsonRpcRouteItem)
async def get_default_route(account: AccountIdentityDep, gateway_id: str) -> JsonRpcRouteItem:
    return await JsonRpcRouteManager.get_default(account.id, gateway_id)


@router.put('/jsonrpc-route', response_model=JsonRpcRouteItem)
async def replace_default_route(
    account: AccountIdentityDep,
    gateway_id: str,
    params: ReplaceJsonRpcRouteParams,
) -> JsonRpcRouteItem:
    return await JsonRpcRouteManager.replace_default(account.id, account.id, gateway_id, params)


@router.get('/jsonrpc-method-routes', response_model=JsonRpcMethodRouteList)
async def list_method_routes(account: AccountIdentityDep, gateway_id: str) -> JsonRpcMethodRouteList:
    return await JsonRpcRouteManager.list_methods(account.id, gateway_id)


@router.post('/jsonrpc-method-routes', response_model=JsonRpcRouteItem, status_code=status.HTTP_201_CREATED)
async def create_method_route(
    account: AccountIdentityDep,
    gateway_id: str,
    params: CreateJsonRpcMethodRouteParams,
) -> JsonRpcRouteItem:
    return await JsonRpcRouteManager.create_method(account.id, account.id, gateway_id, params)


@router.put('/jsonrpc-method-routes/{route_id}', response_model=JsonRpcRouteItem)
async def replace_method_route(
    account: AccountIdentityDep,
    gateway_id: str,
    route_id: str,
    params: ReplaceJsonRpcMethodRouteParams,
) -> JsonRpcRouteItem:
    return await JsonRpcRouteManager.replace_method(account.id, account.id, gateway_id, route_id, params)


@router.delete('/jsonrpc-method-routes/{route_id}', response_model=JsonRpcRouteItem)
async def delete_method_route(
    account: AccountIdentityDep,
    gateway_id: str,
    route_id: str,
    params: Annotated[DeleteJsonRpcMethodRouteParams, Query()],
) -> JsonRpcRouteItem:
    return await JsonRpcRouteManager.delete_method(account.id, account.id, gateway_id, route_id, params.expected_version)
