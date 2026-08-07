from typing import Annotated

from fastapi import Query

from app.api import BaseRouter, DashRouter
from app.api.deps import AdminIdentityDep, JsonRpcRateLimitPolicyManagerDep
from app.model.jsonrpc_rate_limit import (
    JsonRpcRateLimitAuditEventList,
    JsonRpcRateLimitAuditListParams,
    JsonRpcRateLimitPolicyItem,
    UpdateJsonRpcRateLimitPolicyParams,
)

router = BaseRouter(prefix='/jsonrpc-rate-limit-policy', route_class=DashRouter)


@router.get('', response_model=JsonRpcRateLimitPolicyItem)
async def get_rate_limit_policy(
    _admin: AdminIdentityDep,
    manager: JsonRpcRateLimitPolicyManagerDep,
) -> JsonRpcRateLimitPolicyItem:
    return manager.get_policy()


@router.patch('', response_model=JsonRpcRateLimitPolicyItem)
async def update_rate_limit_policy(
    admin: AdminIdentityDep,
    manager: JsonRpcRateLimitPolicyManagerDep,
    params: UpdateJsonRpcRateLimitPolicyParams,
) -> JsonRpcRateLimitPolicyItem:
    """Update the public JSON-RPC admission policy using optimistic version control.

    `max_inflight_per_worker` limits the simultaneous JSON-RPC requests handled by each API process and is always
    enforced. `mode` controls only the request-per-second limits; disabling those limits does not disable the simultaneous
    request limit.
    """
    return await manager.update_policy(admin.id, params)


@router.get('/audit-events', response_model=JsonRpcRateLimitAuditEventList)
async def list_rate_limit_audits(
    _admin: AdminIdentityDep,
    manager: JsonRpcRateLimitPolicyManagerDep,
    params: Annotated[JsonRpcRateLimitAuditListParams, Query()],
) -> JsonRpcRateLimitAuditEventList:
    return await manager.list_audit_events(page=params.page, size=params.size)
