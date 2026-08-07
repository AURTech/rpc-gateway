from typing import Annotated

from fastapi import Query

from app.api import BaseRouter, DashRouter
from app.api.deps import AdminIdentityDep, HttpApiRateLimitPolicyManagerDep
from app.model.http_api_rate_limit import (
    HttpApiRateLimitAuditEventList,
    HttpApiRateLimitAuditListParams,
    HttpApiRateLimitPolicyItem,
    UpdateHttpApiRateLimitPolicyParams,
)

router = BaseRouter(prefix='/http-api-rate-limit-policy', route_class=DashRouter)


@router.get('', response_model=HttpApiRateLimitPolicyItem)
async def get_rate_limit_policy(
    _admin: AdminIdentityDep,
    manager: HttpApiRateLimitPolicyManagerDep,
) -> HttpApiRateLimitPolicyItem:
    return manager.get_policy()


@router.patch('', response_model=HttpApiRateLimitPolicyItem)
async def update_rate_limit_policy(
    admin: AdminIdentityDep,
    manager: HttpApiRateLimitPolicyManagerDep,
    params: UpdateHttpApiRateLimitPolicyParams,
) -> HttpApiRateLimitPolicyItem:
    return await manager.update_policy(admin.id, params)


@router.get('/audit-events', response_model=HttpApiRateLimitAuditEventList)
async def list_rate_limit_audits(
    _admin: AdminIdentityDep,
    manager: HttpApiRateLimitPolicyManagerDep,
    params: Annotated[HttpApiRateLimitAuditListParams, Query()],
) -> HttpApiRateLimitAuditEventList:
    return await manager.list_audit_events(page=params.page, size=params.size)
