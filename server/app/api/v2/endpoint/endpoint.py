from typing import Annotated

from fastapi import Depends, Query, Request, Response, status
from pyrate_limiter import Duration, Rate

from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep, EndpointHealthCheckManagerDep, EndpointManagerDep
from app.core import context
from app.core.private_cache import apply_private_cache
from app.middleware.limiter import RedisRateLimiter
from app.model.auth import PersonalAccessTokenScope
from app.model.endpoint import (
    BulkDeleteEndpointParams,
    BulkDeleteEndpointResult,
    CreateEndpointParams,
    EndpointAuditEventList,
    EndpointAuditListParams,
    EndpointDeleteResult,
    EndpointDetail,
    EndpointHealthCheck,
    EndpointItem,
    EndpointList,
    EndpointListParams,
    UpdateEndpointParams,
    redact_endpoint_detail,
)

router = BaseRouter(prefix='/endpoints', route_class=DashRouter)


async def _health_check_ip_identifier(request: Request) -> str:
    return context.client_ip(request) or '127.0.0.1'


health_check_ip_rate_limit = RedisRateLimiter(
    rates=[Rate(60, Duration.MINUTE)],
    bucket_key='endpoint-health-check-ip',
    identifier=_health_check_ip_identifier,
)
health_check_account_rate_limit = RedisRateLimiter(
    rates=[Rate(30, Duration.MINUTE)],
    bucket_key='endpoint-health-check-account',
)
health_check_endpoint_rate_limit = RedisRateLimiter(
    rates=[Rate(3, Duration.MINUTE)],
    bucket_key='endpoint-health-check-endpoint',
)


@router.post('', response_model=EndpointDetail | EndpointItem, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    response: Response,
    account: AccountIdentityDep,
    manager: EndpointManagerDep,
    params: CreateEndpointParams,
) -> EndpointDetail | EndpointItem:
    """Create a manual endpoint with encrypted URL and auth secret."""
    value = await manager.create_endpoint(account.id, account.id, params)
    apply_private_cache(response.headers)
    if account.uses_pat and PersonalAccessTokenScope.ENDPOINT_SECRETS_READ not in account.pat_scopes:
        return redact_endpoint_detail(value)
    return value


@router.get('', response_model=EndpointList)
async def list_endpoints(
    response: Response,
    account: AccountIdentityDep,
    manager: EndpointManagerDep,
    params: Annotated[EndpointListParams, Query()],
) -> EndpointList:
    """List endpoint registry entries owned by the authenticated account."""
    value = await manager.list_endpoints(
        account.id,
        chain=params.chain,
        network=params.network,
        protocol=params.protocol,
        enabled=params.enabled,
        origin_type=params.origin_type,
        provider_id=params.provider_id,
        page=params.page,
        size=params.size,
    )
    apply_private_cache(response.headers)
    return value


@router.post('/bulk-delete', response_model=BulkDeleteEndpointResult)
async def bulk_delete_endpoints(
    account: AccountIdentityDep,
    manager: EndpointManagerDep,
    params: BulkDeleteEndpointParams,
) -> BulkDeleteEndpointResult:
    """Soft-delete unreferenced manual Endpoints and report active route references."""
    return await manager.bulk_delete_endpoints(account.id, account.id, params)


@router.get('/{endpoint_id}', response_model=EndpointDetail | EndpointItem)
async def get_endpoint(
    response: Response,
    account: AccountIdentityDep,
    manager: EndpointManagerDep,
    endpoint_id: str,
) -> EndpointDetail | EndpointItem:
    """Return one owned endpoint with its displayable URL."""
    value = await manager.get_endpoint(account.id, endpoint_id)
    apply_private_cache(response.headers)
    if account.uses_pat and PersonalAccessTokenScope.ENDPOINT_SECRETS_READ not in account.pat_scopes:
        return redact_endpoint_detail(value)
    return value


@router.patch('/{endpoint_id}', response_model=EndpointDetail | EndpointItem)
async def update_endpoint(
    response: Response,
    account: AccountIdentityDep,
    manager: EndpointManagerDep,
    endpoint_id: str,
    params: UpdateEndpointParams,
) -> EndpointDetail | EndpointItem:
    """Update an endpoint only when expected_version matches its registry version."""
    value = await manager.update_endpoint(account.id, account.id, endpoint_id, params)
    apply_private_cache(response.headers)
    if account.uses_pat and PersonalAccessTokenScope.ENDPOINT_SECRETS_READ not in account.pat_scopes:
        return redact_endpoint_detail(value)
    return value


@router.delete('/{endpoint_id}', response_model=EndpointDeleteResult)
async def delete_endpoint(account: AccountIdentityDep, manager: EndpointManagerDep, endpoint_id: str) -> EndpointDeleteResult:
    """Soft-delete an owned endpoint."""
    return await manager.delete_endpoint(account.id, account.id, endpoint_id)


@router.post(
    '/{endpoint_id}/health-checks',
    response_model=EndpointHealthCheck,
    dependencies=[Depends(health_check_ip_rate_limit)],
)
async def check_endpoint_health(
    request: Request,
    response: Response,
    account: AccountIdentityDep,
    health_manager: EndpointHealthCheckManagerDep,
    endpoint_id: str,
) -> EndpointHealthCheck:
    """Run the fixed, single-request health probe for an owned Endpoint."""
    await health_check_account_rate_limit.acquire(request, response, account.id)
    endpoint_rate_key = f'{account.id}:{endpoint_id}'
    await health_check_endpoint_rate_limit.acquire(request, response, endpoint_rate_key)
    value = await health_manager.check(account.id, endpoint_id)
    apply_private_cache(response.headers)
    return value


@router.get('/{endpoint_id}/audit-events', response_model=EndpointAuditEventList)
async def list_endpoint_audit_events(
    account: AccountIdentityDep,
    manager: EndpointManagerDep,
    endpoint_id: str,
    params: Annotated[EndpointAuditListParams, Query()],
) -> EndpointAuditEventList:
    """List sanitized audit metadata for an owned endpoint."""
    return await manager.list_audit_events(
        account.id,
        endpoint_id,
        page=params.page,
        size=params.size,
    )
