from app.api import BaseRouter
from app.api.v2 import (
    account,
    application,
    auth,
    endpoint,
    gateway,
    http_api_rate_limit,
    http_api_route,
    jsonrpc_rate_limit,
    jsonrpc_route,
    meta,
    overview,
    provider,
    usage,
)

v2_router = BaseRouter()
v2_router.include_router(auth.router, tags=['auth'])
v2_router.include_router(account.router, tags=['accounts'])
v2_router.include_router(application.router, tags=['apps'])
v2_router.include_router(endpoint.router, tags=['endpoints'])
v2_router.include_router(provider.router, tags=['providers'])
v2_router.include_router(gateway.router, tags=['gateways'])
v2_router.include_router(jsonrpc_route.router, tags=['jsonrpc-routes'])
v2_router.include_router(jsonrpc_rate_limit.router, tags=['jsonrpc-rate-limit-policy'])
v2_router.include_router(http_api_route.router, tags=['http-api-routes'])
v2_router.include_router(http_api_rate_limit.router, tags=['http-api-rate-limit-policy'])
v2_router.include_router(usage.router, tags=['usage'])
v2_router.include_router(overview.router, tags=['overview'])
v2_router.include_router(meta.router, tags=['meta'])
