from dataclasses import dataclass
from datetime import datetime

from fastlog import log
from tortoise.backends.base.client import BaseDBAsyncClient

from app.core.errors import BadRequestError, NotfoundError
from app.infra.db import in_tx
from app.model.application import AppAuditAction
from app.model.endpoint import (
    EndpointRouteBindingDeleteResult,
    EndpointRouteBindingItem,
    EndpointRouteBindingList,
    EndpointRouteGatewayItem,
    EndpointRouteStrategyType,
    EndpointRouteType,
)
from app.orm.endpoint import Endpoint
from app.orm.http_api_route import HttpApiRoute, HttpApiRouteTarget
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteScope, JsonRpcRouteTarget
from app.services.application.audit import write_audit_event
from app.util import datetime as datetime_util

_DEFAULT_METHOD = ''


@dataclass(frozen=True, slots=True)
class _BindingEntry:
    item: EndpointRouteBindingItem
    route_created_at: datetime


class EndpointRouteBindingManager:
    @staticmethod
    async def delete_all_bindings(
        account_id: str,
        actor_id: str,
        endpoint_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        """Remove an Endpoint from every active route in one transaction."""
        jsonrpc_targets = await (
            JsonRpcRouteTarget.filter(
                endpoint_id=endpoint_id,
                deleted_at=None,
                route__deleted_at=None,
                route__gateway__deleted_at=None,
                route__gateway__app__account_id=account_id,
                route__gateway__app__deleted_at=None,
            )
            .using_db(using_db)
            .order_by('route_id')
        )
        for target in jsonrpc_targets:
            route = await JsonRpcRoute.select_for_update(using_db=using_db).filter(id=target.route_id, deleted_at=None).first()
            if route is None:
                continue
            await route.fetch_related('gateway', using_db=using_db)
            scopes = await JsonRpcRouteScope.filter(route_id=route.id, deleted_at=None).using_db(using_db)
            is_default = [scope.method for scope in scopes] == [_DEFAULT_METHOD]
            target_count = await JsonRpcRouteTarget.filter(route_id=route.id, deleted_at=None).using_db(using_db).count()
            if not is_default and target_count == 1:
                await write_audit_event(
                    route.gateway.app_id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='jsonrpc_route',
                    resource_id=route.id,
                    action=AppAuditAction.DELETED,
                    previous_version=route.version,
                    new_version=None,
                    changed_fields=['deleted_at'],
                    using_db=using_db,
                )
                await JsonRpcRouteTarget.filter(route_id=route.id).using_db(using_db).delete()
                await JsonRpcRouteScope.filter(route_id=route.id).using_db(using_db).delete()
                await route.delete(using_db=using_db)
                continue
            await target.delete(using_db=using_db)
            await EndpointRouteBindingManager._reindex_jsonrpc(route.id, using_db=using_db)
            await EndpointRouteBindingManager._update_jsonrpc_route(
                route,
                account_id=account_id,
                actor_id=actor_id,
                using_db=using_db,
            )

        http_targets = await (
            HttpApiRouteTarget.filter(
                endpoint_id=endpoint_id,
                deleted_at=None,
                route__deleted_at=None,
                route__gateway__deleted_at=None,
                route__gateway__app__account_id=account_id,
                route__gateway__app__deleted_at=None,
            )
            .using_db(using_db)
            .order_by('route_id')
        )
        for target in http_targets:
            route = await HttpApiRoute.select_for_update(using_db=using_db).filter(id=target.route_id, deleted_at=None).first()
            if route is None:
                continue
            await route.fetch_related('gateway', using_db=using_db)
            await target.delete(using_db=using_db)
            await EndpointRouteBindingManager._reindex_http_api(route.id, using_db=using_db)
            await EndpointRouteBindingManager._update_http_api_route(
                route,
                account_id=account_id,
                actor_id=actor_id,
                using_db=using_db,
            )

    @staticmethod
    async def list_bindings(account_id: str, endpoint_id: str) -> EndpointRouteBindingList:
        await EndpointRouteBindingManager._get_endpoint(account_id, endpoint_id)
        entries = [
            *await EndpointRouteBindingManager._list_jsonrpc(account_id, endpoint_id),
            *await EndpointRouteBindingManager._list_http_api(account_id, endpoint_id),
        ]
        entries.sort(
            key=lambda entry: (
                entry.item.gateway.name.casefold(),
                entry.item.gateway.id,
                entry.route_created_at,
                entry.item.route_id,
            )
        )
        items = [entry.item for entry in entries]
        return EndpointRouteBindingList(total=len(items), items=items)

    @staticmethod
    async def delete_binding(
        account_id: str,
        actor_id: str,
        endpoint_id: str,
        route_type: EndpointRouteType,
        route_id: str,
        expected_version: int,
    ) -> EndpointRouteBindingDeleteResult:
        """Remove one Endpoint target while preserving route ordering and audit history.

        A JSON-RPC method route is deleted when its final target is removed. Default JSON-RPC and HTTP API routes remain
        present with an empty target list. All mutations use optimistic route versions and one database transaction.
        """
        if route_type is EndpointRouteType.HTTP_API:
            result = await EndpointRouteBindingManager._delete_http_api(
                account_id,
                actor_id,
                endpoint_id,
                route_id,
                expected_version,
            )
        else:
            result = await EndpointRouteBindingManager._delete_jsonrpc(
                account_id,
                actor_id,
                endpoint_id,
                route_type,
                route_id,
                expected_version,
            )
        log.info(
            f'Endpoint route binding deleted | Account:{account_id} | Endpoint:{endpoint_id} | '
            f'Route:{route_id} | Type:{route_type.value}'
        )
        return result

    @staticmethod
    async def _get_endpoint(account_id: str, endpoint_id: str) -> Endpoint:
        endpoint = await Endpoint.filter(id=endpoint_id, account_id=account_id, deleted_at=None).first()
        if endpoint is None:
            raise NotfoundError('Endpoint not found.')
        return endpoint

    @staticmethod
    async def _list_jsonrpc(account_id: str, endpoint_id: str) -> list[_BindingEntry]:
        targets = await (
            JsonRpcRouteTarget.filter(
                endpoint_id=endpoint_id,
                deleted_at=None,
                route__deleted_at=None,
                route__gateway__deleted_at=None,
                route__gateway__app__account_id=account_id,
                route__gateway__app__deleted_at=None,
            )
            .select_related('route', 'route__gateway')
            .order_by('route_id')
        )
        if not targets:
            return []
        route_ids = [target.route_id for target in targets]
        scopes = await JsonRpcRouteScope.filter(route_id__in=route_ids, deleted_at=None).order_by('method', 'id')
        methods_by_route: dict[str, list[str]] = {}
        for scope in scopes:
            methods_by_route.setdefault(scope.route_id, []).append(scope.method)
        counts = await EndpointRouteBindingManager._jsonrpc_target_counts(route_ids)
        entries: list[_BindingEntry] = []
        for target in targets:
            route = target.route
            gateway = route.gateway
            methods = methods_by_route.get(route.id, [])
            is_default = methods == [_DEFAULT_METHOD]
            route_type = EndpointRouteType.JSONRPC_DEFAULT if is_default else EndpointRouteType.JSONRPC_METHOD
            entries.append(
                _BindingEntry(
                    route_created_at=route.created_at,
                    item=EndpointRouteBindingItem(
                        route_type=route_type,
                        route_id=route.id,
                        route_version=route.version,
                        strategy_type=EndpointRouteStrategyType(route.strategy_type),
                        methods=[] if is_default else methods,
                        target_count=counts[route.id],
                        gateway=EndpointRouteGatewayItem(id=gateway.id, app_id=gateway.app_id, name=gateway.name),
                    ),
                ),
            )
        return entries

    @staticmethod
    async def _list_http_api(account_id: str, endpoint_id: str) -> list[_BindingEntry]:
        targets = await (
            HttpApiRouteTarget.filter(
                endpoint_id=endpoint_id,
                deleted_at=None,
                route__deleted_at=None,
                route__gateway__deleted_at=None,
                route__gateway__app__account_id=account_id,
                route__gateway__app__deleted_at=None,
            )
            .select_related('route', 'route__gateway')
            .order_by('route_id')
        )
        if not targets:
            return []
        route_ids = [target.route_id for target in targets]
        counts = await EndpointRouteBindingManager._http_api_target_counts(route_ids)
        return [
            _BindingEntry(
                route_created_at=target.route.created_at,
                item=EndpointRouteBindingItem(
                    route_type=EndpointRouteType.HTTP_API,
                    route_id=target.route.id,
                    route_version=target.route.version,
                    strategy_type=EndpointRouteStrategyType(target.route.strategy_type),
                    methods=[],
                    target_count=counts[target.route.id],
                    gateway=EndpointRouteGatewayItem(
                        id=target.route.gateway.id,
                        app_id=target.route.gateway.app_id,
                        name=target.route.gateway.name,
                    ),
                ),
            )
            for target in targets
        ]

    @staticmethod
    async def _jsonrpc_target_counts(route_ids: list[str]) -> dict[str, int]:
        rows = await JsonRpcRouteTarget.filter(route_id__in=route_ids, deleted_at=None).only('route_id')
        counts = dict.fromkeys(route_ids, 0)
        for row in rows:
            counts[row.route_id] += 1
        return counts

    @staticmethod
    async def _http_api_target_counts(route_ids: list[str]) -> dict[str, int]:
        rows = await HttpApiRouteTarget.filter(route_id__in=route_ids, deleted_at=None).only('route_id')
        counts = dict.fromkeys(route_ids, 0)
        for row in rows:
            counts[row.route_id] += 1
        return counts

    @staticmethod
    async def _delete_jsonrpc(
        account_id: str,
        actor_id: str,
        endpoint_id: str,
        route_type: EndpointRouteType,
        route_id: str,
        expected_version: int,
    ) -> EndpointRouteBindingDeleteResult:
        await EndpointRouteBindingManager._get_endpoint(account_id, endpoint_id)
        async with in_tx() as connection:
            route = await (
                JsonRpcRoute.select_for_update(using_db=connection)
                .filter(
                    id=route_id,
                    deleted_at=None,
                    gateway__deleted_at=None,
                    gateway__app__account_id=account_id,
                    gateway__app__deleted_at=None,
                )
                .select_related('gateway')
                .first()
            )
            if route is None:
                raise NotfoundError('Route binding not found.')
            if route.version != expected_version:
                raise BadRequestError('Route version conflict. Reload the Endpoint before saving.')
            scopes = await JsonRpcRouteScope.filter(route_id=route.id, deleted_at=None).using_db(connection)
            methods = [scope.method for scope in scopes]
            is_default = methods == [_DEFAULT_METHOD]
            requested_default = route_type is EndpointRouteType.JSONRPC_DEFAULT
            if is_default != requested_default:
                raise NotfoundError('Route binding not found.')
            target = await JsonRpcRouteTarget.select_for_update(using_db=connection).get_or_none(
                route_id=route.id,
                endpoint_id=endpoint_id,
                deleted_at=None,
            )
            if target is None:
                raise NotfoundError('Route binding not found.')
            target_count = await JsonRpcRouteTarget.filter(route_id=route.id, deleted_at=None).using_db(connection).count()
            if not is_default and target_count == 1:
                await write_audit_event(
                    route.gateway.app_id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='jsonrpc_route',
                    resource_id=route.id,
                    action=AppAuditAction.DELETED,
                    previous_version=route.version,
                    new_version=None,
                    changed_fields=['deleted_at'],
                    using_db=connection,
                )
                await JsonRpcRouteTarget.filter(route_id=route.id).using_db(connection).delete()
                await JsonRpcRouteScope.filter(route_id=route.id).using_db(connection).delete()
                await route.delete(using_db=connection)
                return EndpointRouteBindingDeleteResult(
                    endpoint_id=endpoint_id,
                    route_type=route_type,
                    route_id=route.id,
                    route_deleted=True,
                )
            await target.delete(using_db=connection)
            await EndpointRouteBindingManager._reindex_jsonrpc(route.id, using_db=connection)
            version = await EndpointRouteBindingManager._update_jsonrpc_route(
                route,
                account_id=account_id,
                actor_id=actor_id,
                using_db=connection,
            )
            return EndpointRouteBindingDeleteResult(
                endpoint_id=endpoint_id,
                route_type=route_type,
                route_id=route.id,
                route_deleted=False,
                route_version=version,
            )

    @staticmethod
    async def _delete_http_api(
        account_id: str,
        actor_id: str,
        endpoint_id: str,
        route_id: str,
        expected_version: int,
    ) -> EndpointRouteBindingDeleteResult:
        await EndpointRouteBindingManager._get_endpoint(account_id, endpoint_id)
        async with in_tx() as connection:
            route = await (
                HttpApiRoute.select_for_update(using_db=connection)
                .filter(
                    id=route_id,
                    deleted_at=None,
                    gateway__deleted_at=None,
                    gateway__app__account_id=account_id,
                    gateway__app__deleted_at=None,
                )
                .select_related('gateway')
                .first()
            )
            if route is None:
                raise NotfoundError('Route binding not found.')
            if route.version != expected_version:
                raise BadRequestError('Route version conflict. Reload the Endpoint before saving.')
            target = await HttpApiRouteTarget.select_for_update(using_db=connection).get_or_none(
                route_id=route.id,
                endpoint_id=endpoint_id,
                deleted_at=None,
            )
            if target is None:
                raise NotfoundError('Route binding not found.')
            await target.delete(using_db=connection)
            await EndpointRouteBindingManager._reindex_http_api(route.id, using_db=connection)
            version = await EndpointRouteBindingManager._update_http_api_route(
                route,
                account_id=account_id,
                actor_id=actor_id,
                using_db=connection,
            )
            return EndpointRouteBindingDeleteResult(
                endpoint_id=endpoint_id,
                route_type=EndpointRouteType.HTTP_API,
                route_id=route.id,
                route_deleted=False,
                route_version=version,
            )

    @staticmethod
    async def _reindex_jsonrpc(route_id: str, *, using_db: BaseDBAsyncClient) -> None:
        targets = await JsonRpcRouteTarget.filter(route_id=route_id, deleted_at=None).using_db(using_db).order_by('position')
        changed: list[JsonRpcRouteTarget] = []
        for position, target in enumerate(targets):
            if target.position == position:
                continue
            target.position = position
            changed.append(target)
        if changed:
            await JsonRpcRouteTarget.bulk_update(changed, fields=['position'], using_db=using_db)

    @staticmethod
    async def _reindex_http_api(route_id: str, *, using_db: BaseDBAsyncClient) -> None:
        targets = await HttpApiRouteTarget.filter(route_id=route_id, deleted_at=None).using_db(using_db).order_by('position')
        changed: list[HttpApiRouteTarget] = []
        for position, target in enumerate(targets):
            if target.position == position:
                continue
            target.position = position
            changed.append(target)
        if changed:
            await HttpApiRouteTarget.bulk_update(changed, fields=['position'], using_db=using_db)

    @staticmethod
    async def _update_jsonrpc_route(
        route: JsonRpcRoute,
        *,
        account_id: str,
        actor_id: str,
        using_db: BaseDBAsyncClient,
    ) -> int:
        previous_version = route.version
        version = previous_version + 1
        modified_at = datetime_util.next_utc_timestamp(route.modified_at)
        await JsonRpcRoute.filter(id=route.id).using_db(using_db).update(version=version, modified_at=modified_at)
        await write_audit_event(
            route.gateway.app_id,
            account_id=account_id,
            actor_id=actor_id,
            resource_type='jsonrpc_route',
            resource_id=route.id,
            action=AppAuditAction.UPDATED,
            previous_version=previous_version,
            new_version=version,
            changed_fields=['targets'],
            using_db=using_db,
        )
        return version

    @staticmethod
    async def _update_http_api_route(
        route: HttpApiRoute,
        *,
        account_id: str,
        actor_id: str,
        using_db: BaseDBAsyncClient,
    ) -> int:
        previous_version = route.version
        version = previous_version + 1
        modified_at = datetime_util.next_utc_timestamp(route.modified_at)
        await HttpApiRoute.filter(id=route.id).using_db(using_db).update(version=version, modified_at=modified_at)
        await write_audit_event(
            route.gateway.app_id,
            account_id=account_id,
            actor_id=actor_id,
            resource_type='http_api_route',
            resource_id=route.id,
            action=AppAuditAction.UPDATED,
            previous_version=previous_version,
            new_version=version,
            changed_fields=['targets'],
            using_db=using_db,
        )
        return version
