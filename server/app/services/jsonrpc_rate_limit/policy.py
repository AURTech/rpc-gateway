import asyncio
from contextlib import suppress

from fastlog import log

from app.core.auth_context import get_pat_id
from app.core.errors import BadRequestError
from app.infra.db import in_tx
from app.model.admission import AdmissionMode
from app.model.jsonrpc_rate_limit import (
    JsonRpcRateLimitAuditEventItem,
    JsonRpcRateLimitAuditEventList,
    JsonRpcRateLimitBucket,
    JsonRpcRateLimitPolicyItem,
    UpdateJsonRpcRateLimitPolicyParams,
)
from app.orm.jsonrpc_rate_limit import JsonRpcRateLimitAuditEvent, JsonRpcRateLimitPolicy
from app.util import datetime as datetime_util

PUBLIC_JSONRPC_POLICY_NAME = 'public-jsonrpc'


def _to_item(row: JsonRpcRateLimitPolicy) -> JsonRpcRateLimitPolicyItem:
    return JsonRpcRateLimitPolicyItem(
        mode=AdmissionMode(row.mode),
        max_inflight_per_worker=row.max_inflight_per_worker,
        redis_timeout_ms=row.redis_timeout_ms,
        redis_admission_per_worker=row.redis_admission_per_worker,
        fallback_max_keys_per_worker=row.fallback_max_keys_per_worker,
        global_limit=JsonRpcRateLimitBucket(rps=row.global_rps, burst=row.global_burst),
        ip_limit=JsonRpcRateLimitBucket(rps=row.ip_rps, burst=row.ip_burst),
        account_limit=JsonRpcRateLimitBucket(rps=row.account_rps, burst=row.account_burst),
        app_limit=JsonRpcRateLimitBucket(rps=row.app_rps, burst=row.app_burst),
        version=row.version,
        modified_by_account_id=row.modified_by_account_id,
        created_at=row.created_at,
        modified_at=row.modified_at,
    )


def _updates(params: UpdateJsonRpcRateLimitPolicyParams) -> dict[str, object]:
    fields = params.model_fields_set
    updates: dict[str, object] = {}
    if 'mode' in fields and params.mode is not None:
        updates['mode'] = params.mode
    if 'max_inflight_per_worker' in fields and params.max_inflight_per_worker is not None:
        updates['max_inflight_per_worker'] = params.max_inflight_per_worker
    if 'redis_timeout_ms' in fields and params.redis_timeout_ms is not None:
        updates['redis_timeout_ms'] = params.redis_timeout_ms
    if 'redis_admission_per_worker' in fields and params.redis_admission_per_worker is not None:
        updates['redis_admission_per_worker'] = params.redis_admission_per_worker
    if 'fallback_max_keys_per_worker' in fields and params.fallback_max_keys_per_worker is not None:
        updates['fallback_max_keys_per_worker'] = params.fallback_max_keys_per_worker
    if 'global_limit' in fields and params.global_limit is not None:
        updates['global_limit'] = params.global_limit
    if 'ip_limit' in fields and params.ip_limit is not None:
        updates['ip_limit'] = params.ip_limit
    if 'account_limit' in fields and params.account_limit is not None:
        updates['account_limit'] = params.account_limit
    if 'app_limit' in fields and params.app_limit is not None:
        updates['app_limit'] = params.app_limit
    return updates


def _orm_values(policy: JsonRpcRateLimitPolicyItem) -> dict[str, object]:
    values = policy.model_dump(exclude={'global_limit', 'ip_limit', 'account_limit', 'app_limit', 'created_at'})
    values.update(
        {
            'global_rps': policy.global_limit.rps,
            'global_burst': policy.global_limit.burst,
            'ip_rps': policy.ip_limit.rps,
            'ip_burst': policy.ip_limit.burst,
            'account_rps': policy.account_limit.rps,
            'account_burst': policy.account_limit.burst,
            'app_rps': policy.app_limit.rps,
            'app_burst': policy.app_limit.burst,
        }
    )
    return values


class JsonRpcRateLimitPolicyManager:
    def __init__(self, *, refresh_seconds: float) -> None:
        self._refresh_seconds = refresh_seconds
        self._policy: JsonRpcRateLimitPolicyItem | None = None
        self._refresh_task: asyncio.Task[None] | None = None

    def get_policy(self) -> JsonRpcRateLimitPolicyItem:
        policy = self._policy
        if policy is None:
            raise RuntimeError('JSON-RPC rate limit policy manager has not started.')
        return policy

    async def start(self) -> None:
        """Load the authoritative policy and start bounded cross-process refresh."""
        if self._refresh_task is not None:
            return
        row, _created = await JsonRpcRateLimitPolicy.get_or_create(name=PUBLIC_JSONRPC_POLICY_NAME)
        self._publish(_to_item(row))
        self._refresh_task = asyncio.create_task(self._refresh_loop(), name='jsonrpc-rate-limit-policy-refresh')

    async def close(self) -> None:
        task = self._refresh_task
        self._refresh_task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def update_policy(self, actor_id: str, params: UpdateJsonRpcRateLimitPolicyParams) -> JsonRpcRateLimitPolicyItem:
        """Update the singleton policy and audit the version change atomically."""
        async with in_tx() as connection:
            row = await JsonRpcRateLimitPolicy.select_for_update(using_db=connection).get_or_none(
                name=PUBLIC_JSONRPC_POLICY_NAME,
                deleted_at=None,
            )
            if row is None:
                raise BadRequestError('JSON-RPC rate limit policy is unavailable.')
            if row.version != params.expected_version:
                raise BadRequestError('JSON-RPC rate limit policy version conflict. Reload the policy before saving.')
            saved = _to_item(row)
            updates = _updates(params)
            saved_values = saved.model_dump()
            candidate = saved.model_copy(update=updates)
            candidate_values = candidate.model_dump()
            changed_fields = [name for name in updates if candidate_values[name] != saved_values[name]]
            if not changed_fields:
                return saved
            modified_at = datetime_util.next_utc_timestamp(row.modified_at)
            policy = candidate.model_copy(
                update={
                    **updates,
                    'version': row.version + 1,
                    'modified_by_account_id': actor_id,
                    'modified_at': modified_at,
                }
            )
            await JsonRpcRateLimitPolicy.filter(id=row.id).using_db(connection).update(**_orm_values(policy))
            await JsonRpcRateLimitAuditEvent.create(
                using_db=connection,
                policy_id=row.id,
                actor_id=actor_id,
                actor_token_id=get_pat_id(),
                previous_version=row.version,
                new_version=policy.version,
                changed_fields=changed_fields,
            )
        self._publish(policy)
        log.info(f'JSON-RPC rate limit policy updated | Actor:{actor_id} | Version:{policy.version}')
        return policy

    async def list_audit_events(self, *, page: int, size: int) -> JsonRpcRateLimitAuditEventList:
        policy = await JsonRpcRateLimitPolicy.get_or_none(name=PUBLIC_JSONRPC_POLICY_NAME, deleted_at=None)
        if policy is None:
            raise BadRequestError('JSON-RPC rate limit policy is unavailable.')
        query = JsonRpcRateLimitAuditEvent.filter(policy_id=policy.id, deleted_at=None)
        total = await query.count()
        rows = await query.order_by('-created_at', 'id').offset((page - 1) * size).limit(size)
        items = [
            JsonRpcRateLimitAuditEventItem(
                id=row.id,
                actor_id=row.actor_id,
                actor_token_id=row.actor_token_id,
                previous_version=row.previous_version,
                new_version=row.new_version,
                changed_fields=list(row.changed_fields),
                created_at=row.created_at,
            )
            for row in rows
        ]
        max_page = (total + size - 1) // size if size else 0
        return JsonRpcRateLimitAuditEventList(page=page, size=size, total=total, max_page=max_page, items=items)

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._refresh_seconds)
            try:
                row = await JsonRpcRateLimitPolicy.get_or_none(name=PUBLIC_JSONRPC_POLICY_NAME, deleted_at=None)
                if row is not None:
                    self._publish(_to_item(row))
            except Exception as exc:
                log.warning(f'JSON-RPC rate limit policy refresh failed | Error:{exc!r}')

    def _publish(self, policy: JsonRpcRateLimitPolicyItem) -> None:
        saved = self._policy
        if saved is None or policy.version > saved.version:
            self._policy = policy
