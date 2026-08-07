from datetime import datetime

from fastlog import log
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from app.core.errors import BadRequestError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.application import AppAuditAction
from app.model.blockchain import Chain, Network
from app.model.gateway import BulkUpdateGatewayParams, BulkUpdateGatewayResult, GatewayItem, GatewayList, UpdateGatewayParams
from app.model.pagination import DEFAULT_LIST_PAGE_SIZE, ListSort, get_created_at_order
from app.orm.application import App
from app.orm.gateway import Gateway
from app.services.application.audit import write_audit_event
from app.services.gateway.host import build_access_points
from app.util import datetime as datetime_util


class GatewayManager:
    @staticmethod
    async def list_gateways(
        account_id: str,
        *,
        app_id: str | None = None,
        chain: list[Chain] | None = None,
        network: list[Network] | None = None,
        enabled: bool | None = None,
        search: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        sort: ListSort = 'DESC',
        page: int = 1,
        size: int = DEFAULT_LIST_PAGE_SIZE,
    ) -> GatewayList:
        query = Gateway.filter(app__account_id=account_id, app__deleted_at=None, deleted_at=None)
        if app_id is not None:
            query = query.filter(app_id=app_id)
        if chain:
            query = query.filter(chain__in=chain)
        if network:
            query = query.filter(network__in=network)
        if enabled is not None:
            query = query.filter(enabled=enabled)
        if search:
            term = search.strip()
            query = query.filter(Q(name__icontains=term) | Q(id__icontains=term) | Q(app__name__icontains=term))
        if start_at is not None:
            query = query.filter(created_at__gte=start_at)
        if end_at is not None:
            query = query.filter(created_at__lt=end_at)
        total = await query.count()
        rows = await query.select_related('app').order_by(*get_created_at_order(sort)).offset((page - 1) * size).limit(size)
        try:
            items = [GatewayManager._to_item(row) for row in rows]
        except ValueError as exc:
            log.warning(f'Gateway transport snapshot is invalid | Account:{account_id}')
            raise UnavailableError('Gateway configuration is unavailable.') from exc
        max_page = (total + size - 1) // size if size else 0
        return GatewayList(page=page, size=size, total=total, max_page=max_page, items=items)

    @staticmethod
    async def get_gateway(account_id: str, gateway_id: str) -> GatewayItem:
        gateway = await GatewayManager._get_gateway(account_id, gateway_id)
        try:
            return GatewayManager._to_item(gateway)
        except ValueError as exc:
            raise UnavailableError('Gateway configuration is unavailable.') from exc

    @staticmethod
    async def update_gateway(
        account_id: str,
        actor_id: str,
        gateway_id: str,
        params: UpdateGatewayParams,
    ) -> GatewayItem:
        try:
            async with in_tx() as connection:
                gateway = await (
                    Gateway.select_for_update(using_db=connection)
                    .filter(
                        id=gateway_id,
                        app__account_id=account_id,
                        app__deleted_at=None,
                        deleted_at=None,
                    )
                    .select_related('app')
                    .first()
                )
                if gateway is None:
                    raise NotfoundError('Gateway not found.')
                if gateway.version != params.expected_version:
                    raise BadRequestError('Gateway version conflict. Reload the Gateway before saving.')
                values = params.model_dump(exclude={'expected_version'}, exclude_unset=True)
                changed_fields = [name for name, value in values.items() if value != getattr(gateway, name)]
                if not changed_fields:
                    return GatewayManager._to_item(gateway)
                previous_version = gateway.version
                new_version = previous_version + 1
                values['version'] = new_version
                values['modified_at'] = datetime_util.next_utc_timestamp(gateway.modified_at)
                await Gateway.filter(id=gateway.id).using_db(connection).update(**values)
                gateway.update_from_dict(values)
                await write_audit_event(
                    gateway.app_id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='gateway',
                    resource_id=gateway.id,
                    action=AppAuditAction.UPDATED,
                    previous_version=previous_version,
                    new_version=new_version,
                    changed_fields=changed_fields,
                    using_db=connection,
                )
        except IntegrityError as exc:
            log.warning(f'Gateway name already exists | Account:{account_id} | Gateway:{gateway_id}')
            raise BadRequestError('Gateway name already exists.') from exc
        except ValueError as exc:
            raise UnavailableError('Gateway configuration is unavailable.') from exc
        log.info(f'Gateway {gateway_id} updated | Account:{account_id} | Version:{gateway.version}')
        return GatewayManager._to_item(gateway)

    @staticmethod
    async def bulk_update_gateways(
        account_id: str,
        actor_id: str,
        app_id: str,
        params: BulkUpdateGatewayParams,
    ) -> BulkUpdateGatewayResult:
        """Atomically update Gateway enabled state after validating every target version.

        Raises:
            NotfoundError: the App or any target is unavailable to the account.
            BadRequestError: any target version is stale.

        Side effects:
            Locks all targets, updates changed rows, and records their audit events in one transaction.
        """
        target_by_id = {target.id: target for target in params.gateways}
        gateway_ids = sorted(target_by_id)
        async with in_tx() as connection:
            app = await App.select_for_update(using_db=connection).get_or_none(
                id=app_id,
                account_id=account_id,
                deleted_at=None,
            )
            if app is None:
                raise NotfoundError('App not found.')
            gateways = await (
                Gateway.select_for_update(using_db=connection)
                .filter(
                    id__in=gateway_ids,
                    app_id=app_id,
                    deleted_at=None,
                )
                .order_by('id')
            )
            for gateway in gateways:
                gateway.app = app
            gateways_by_id = {gateway.id: gateway for gateway in gateways}
            if len(gateways_by_id) != len(gateway_ids):
                raise NotfoundError('Gateway not found.')
            for gateway_id in gateway_ids:
                gateway = gateways_by_id[gateway_id]
                if gateway.version != target_by_id[gateway_id].expected_version:
                    raise BadRequestError('Gateway version conflict. Reload the Gateways before saving.')

            changed_gateways: list[Gateway] = []
            previous_versions: dict[str, int] = {}
            for gateway in gateways:
                if gateway.enabled == params.enabled:
                    continue
                previous_versions[gateway.id] = gateway.version
                gateway.enabled = params.enabled
                gateway.version += 1
                gateway.modified_at = datetime_util.next_utc_timestamp(gateway.modified_at)
                changed_gateways.append(gateway)

            if changed_gateways:
                await Gateway.bulk_update(
                    changed_gateways,
                    fields=['enabled', 'version', 'modified_at'],
                    using_db=connection,
                )
                for gateway in changed_gateways:
                    await write_audit_event(
                        gateway.app_id,
                        account_id=account_id,
                        actor_id=actor_id,
                        resource_type='gateway',
                        resource_id=gateway.id,
                        action=AppAuditAction.UPDATED,
                        previous_version=previous_versions[gateway.id],
                        new_version=gateway.version,
                        changed_fields=['enabled'],
                        using_db=connection,
                    )

        try:
            items = [GatewayManager._to_item(gateways_by_id[target.id]) for target in params.gateways]
        except ValueError as exc:
            raise UnavailableError('Gateway configuration is unavailable.') from exc
        log.info(
            f'Gateway statuses updated | Account:{account_id} | App:{app_id} | '
            f'Enabled:{params.enabled} | Count:{len(changed_gateways)}'
        )
        return BulkUpdateGatewayResult(total=len(items), items=items)

    @staticmethod
    async def _get_gateway(account_id: str, gateway_id: str) -> Gateway:
        gateway = await (
            Gateway.filter(
                id=gateway_id,
                app__account_id=account_id,
                app__deleted_at=None,
                deleted_at=None,
            )
            .select_related('app')
            .first()
        )
        if gateway is None:
            raise NotfoundError('Gateway not found.')
        return gateway

    @staticmethod
    def _to_item(gateway: Gateway) -> GatewayItem:
        chain = Chain(gateway.chain)
        network = Network(gateway.network)
        return GatewayItem(
            id=gateway.id,
            app_id=gateway.app_id,
            app_name=gateway.app.name,
            name=gateway.name,
            chain=chain,
            network=network,
            enabled=gateway.enabled,
            effective_enabled=gateway.app.enabled and gateway.enabled,
            version=gateway.version,
            access_points=build_access_points(chain, network, gateway.transport_types),
            created_at=gateway.created_at,
            modified_at=gateway.modified_at,
        )
