from tortoise.backends.base.client import BaseDBAsyncClient

from app.core.auth_context import get_pat_id
from app.model.application import AppAuditAction
from app.orm.application import AppAuditEvent


async def write_audit_event(
    app_id: str,
    *,
    account_id: str,
    actor_id: str,
    resource_type: str,
    resource_id: str,
    action: AppAuditAction,
    previous_version: int | None,
    new_version: int | None,
    changed_fields: list[str],
    using_db: BaseDBAsyncClient,
) -> None:
    await AppAuditEvent.create(
        using_db=using_db,
        app_id=app_id,
        account_id=account_id,
        actor_id=actor_id,
        actor_token_id=get_pat_id(),
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        previous_version=previous_version,
        new_version=new_version,
        changed_fields=changed_fields,
    )
