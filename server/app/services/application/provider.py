from dataclasses import dataclass

from tortoise.backends.base.client import BaseDBAsyncClient

from app.core.errors import NotfoundError
from app.infra.db import in_tx
from app.model.application import AppAuditAction, AppProviderItem, AppProviderResult
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointProtocol
from app.model.http_api_route import HttpApiRoutingStrategyType
from app.model.jsonrpc_route import JsonRpcRoutingStrategyType
from app.orm.application import App
from app.orm.gateway import Gateway
from app.orm.http_api_route import HttpApiRoute, HttpApiRouteTarget
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteScope, JsonRpcRouteTarget
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.application.audit import write_audit_event
from app.util import datetime as datetime_util

_MAX_ROUTE_TARGETS = 100


@dataclass(frozen=True, slots=True)
class RouteBindingStats:
    added: int = 0
    removed: int = 0
    skipped: int = 0

    def merge(self, other: 'RouteBindingStats') -> 'RouteBindingStats':
        return RouteBindingStats(
            added=self.added + other.added,
            removed=self.removed + other.removed,
            skipped=self.skipped + other.skipped,
        )


class AppProviderManager:
    @staticmethod
    async def set_provider(account_id: str, app_id: str, provider_id: str) -> AppProviderResult:
        """Associate one Provider and publish its available Endpoints to enabled App Gateways."""
        async with in_tx() as connection:
            app = await App.select_for_update(using_db=connection).get_or_none(
                id=app_id,
                account_id=account_id,
                deleted_at=None,
            )
            if app is None:
                raise NotfoundError('App not found.')
            provider = await Provider.select_for_update(using_db=connection).get_or_none(
                id=provider_id,
                account_id=account_id,
                deleted_at=None,
                enabled=True,
            )
            if provider is None:
                raise NotfoundError('Provider not found.')
            stats = RouteBindingStats()
            if app.provider_id and app.provider_id != provider.id:
                stats = await AppProviderManager.remove_provider_targets(
                    account_id,
                    app.provider_id,
                    app_id=app.id,
                    using_db=connection,
                )
            if app.provider_id != provider.id:
                previous_version = app.version
                values = {
                    'provider_id': provider.id,
                    'version': previous_version + 1,
                    'modified_at': datetime_util.next_utc_timestamp(app.modified_at),
                }
                await App.filter(id=app.id).using_db(connection).update(**values)
                app.update_from_dict(values)
                await write_audit_event(
                    app.id,
                    account_id=account_id,
                    actor_id=account_id,
                    resource_type='app',
                    resource_id=app.id,
                    action=AppAuditAction.UPDATED,
                    previous_version=previous_version,
                    new_version=app.version,
                    changed_fields=['provider_id'],
                    using_db=connection,
                )
            added = await AppProviderManager.bind_provider_endpoints(
                account_id,
                provider.id,
                app_id=app.id,
                using_db=connection,
            )
            stats = stats.merge(added)
        return AppProviderResult(
            app_id=app.id,
            provider=AppProviderItem(id=provider.id, name=provider.name, vendor=provider.vendor),
            route_targets_added=stats.added,
            route_targets_removed=stats.removed,
            route_targets_skipped=stats.skipped,
        )

    @staticmethod
    async def clear_provider(account_id: str, app_id: str) -> AppProviderResult:
        """Remove the Provider association and only the Route Targets created by that association."""
        async with in_tx() as connection:
            app = await App.select_for_update(using_db=connection).get_or_none(
                id=app_id,
                account_id=account_id,
                deleted_at=None,
            )
            if app is None:
                raise NotfoundError('App not found.')
            stats = RouteBindingStats()
            if app.provider_id:
                stats = await AppProviderManager.remove_provider_targets(
                    account_id,
                    app.provider_id,
                    app_id=app.id,
                    using_db=connection,
                )
                previous_version = app.version
                values = {
                    'provider_id': None,
                    'version': previous_version + 1,
                    'modified_at': datetime_util.next_utc_timestamp(app.modified_at),
                }
                await App.filter(id=app.id).using_db(connection).update(**values)
                app.update_from_dict(values)
                await write_audit_event(
                    app.id,
                    account_id=account_id,
                    actor_id=account_id,
                    resource_type='app',
                    resource_id=app.id,
                    action=AppAuditAction.UPDATED,
                    previous_version=previous_version,
                    new_version=app.version,
                    changed_fields=['provider_id'],
                    using_db=connection,
                )
        return AppProviderResult(
            app_id=app.id,
            provider=None,
            route_targets_added=0,
            route_targets_removed=stats.removed,
            route_targets_skipped=stats.skipped,
        )

    @staticmethod
    async def bind_provider_endpoints(
        account_id: str,
        provider_id: str,
        *,
        app_id: str | None = None,
        using_db: BaseDBAsyncClient,
    ) -> RouteBindingStats:
        """Append available Provider Endpoints to matching default routes without replacing manual targets."""
        app_query = App.filter(provider_id=provider_id, account_id=account_id, deleted_at=None)
        if app_id is not None:
            app_query = app_query.filter(id=app_id)
        apps = await app_query.using_db(using_db).only('id')
        app_ids = [app.id for app in apps]
        if not app_ids:
            return RouteBindingStats()
        bindings = await (
            ProviderEndpointBinding.filter(
                provider_id=provider_id,
                endpoint__account_id=account_id,
                endpoint__deleted_at=None,
                endpoint__enabled=True,
            )
            .using_db(using_db)
            .select_related('endpoint')
            .order_by('endpoint__created_at', 'endpoint_id')
        )
        gateways = await (
            Gateway.filter(app_id__in=app_ids, deleted_at=None, enabled=True)
            .using_db(using_db)
            .order_by('app_id', 'chain', 'network')
        )
        endpoint_ids_by_key: dict[tuple[Chain, Network, EndpointProtocol], list[str]] = {}
        for binding in bindings:
            endpoint = binding.endpoint
            protocol = EndpointProtocol(endpoint.protocol)
            key = (Chain(endpoint.chain), Network(endpoint.network), protocol)
            endpoint_ids_by_key.setdefault(key, []).append(endpoint.id)
        jsonrpc_stats = await AppProviderManager._bind_jsonrpc(
            account_id,
            provider_id,
            gateways,
            endpoint_ids_by_key,
            using_db=using_db,
        )
        http_stats = await AppProviderManager._bind_http_api(
            account_id,
            provider_id,
            gateways,
            endpoint_ids_by_key,
            using_db=using_db,
        )
        return jsonrpc_stats.merge(http_stats)

    @staticmethod
    async def remove_provider_targets(
        account_id: str,
        provider_id: str,
        *,
        app_id: str | None = None,
        endpoint_ids: list[str] | None = None,
        using_db: BaseDBAsyncClient,
    ) -> RouteBindingStats:
        """Delete only targets created by a Provider association and compact their remaining route positions."""
        jsonrpc_query = JsonRpcRouteTarget.filter(
            source_provider_id=provider_id,
            deleted_at=None,
            route__gateway__app__account_id=account_id,
            route__gateway__app__deleted_at=None,
        )
        http_query = HttpApiRouteTarget.filter(
            source_provider_id=provider_id,
            deleted_at=None,
            route__gateway__app__account_id=account_id,
            route__gateway__app__deleted_at=None,
        )
        if app_id is not None:
            jsonrpc_query = jsonrpc_query.filter(route__gateway__app_id=app_id)
            http_query = http_query.filter(route__gateway__app_id=app_id)
        if endpoint_ids is not None:
            jsonrpc_query = jsonrpc_query.filter(endpoint_id__in=endpoint_ids)
            http_query = http_query.filter(endpoint_id__in=endpoint_ids)
        jsonrpc_targets = await jsonrpc_query.using_db(using_db).only('id', 'route_id')
        http_targets = await http_query.using_db(using_db).only('id', 'route_id')
        removed = 0
        for route_id in sorted({target.route_id for target in jsonrpc_targets}):
            target_ids = [target.id for target in jsonrpc_targets if target.route_id == route_id]
            removed += await AppProviderManager._remove_jsonrpc_targets(
                account_id,
                route_id,
                target_ids,
                using_db=using_db,
            )
        for route_id in sorted({target.route_id for target in http_targets}):
            target_ids = [target.id for target in http_targets if target.route_id == route_id]
            removed += await AppProviderManager._remove_http_targets(
                account_id,
                route_id,
                target_ids,
                using_db=using_db,
            )
        return RouteBindingStats(removed=removed)

    @staticmethod
    async def _bind_jsonrpc(
        account_id: str,
        provider_id: str,
        gateways: list[Gateway],
        endpoint_ids_by_key: dict[tuple[Chain, Network, EndpointProtocol], list[str]],
        *,
        using_db: BaseDBAsyncClient,
    ) -> RouteBindingStats:
        stats = RouteBindingStats()
        for gateway in gateways:
            endpoint_ids = endpoint_ids_by_key.get(
                (Chain(gateway.chain), Network(gateway.network), EndpointProtocol.JSONRPC),
                [],
            )
            if not endpoint_ids:
                continue
            scope = await (
                JsonRpcRouteScope.filter(gateway_id=gateway.id, method='', deleted_at=None, route__deleted_at=None)
                .using_db(using_db)
                .first()
            )
            if scope is None:
                continue
            route = await JsonRpcRoute.select_for_update(using_db=using_db).get(id=scope.route_id)
            targets = await (
                JsonRpcRouteTarget.filter(route_id=route.id, deleted_at=None).using_db(using_db).order_by('position')
            )
            existing_ids = {target.endpoint_id for target in targets}
            additions = [endpoint_id for endpoint_id in endpoint_ids if endpoint_id not in existing_ids]
            capacity = max(0, _MAX_ROUTE_TARGETS - len(targets))
            accepted = additions[:capacity]
            skipped = len(additions) - len(accepted)
            if not accepted:
                stats = stats.merge(RouteBindingStats(skipped=skipped))
                continue
            strategy = JsonRpcRoutingStrategyType(route.strategy_type)
            weight = 100 if strategy is JsonRpcRoutingStrategyType.LOAD_BALANCE else None
            rows = [
                JsonRpcRouteTarget(
                    route_id=route.id,
                    endpoint_id=endpoint_id,
                    source_provider_id=provider_id,
                    position=len(targets) + position,
                    weight=weight,
                )
                for position, endpoint_id in enumerate(accepted)
            ]
            await JsonRpcRouteTarget.bulk_create(rows, using_db=using_db)
            await AppProviderManager._touch_jsonrpc(account_id, route, using_db=using_db)
            stats = stats.merge(RouteBindingStats(added=len(rows), skipped=skipped))
        return stats

    @staticmethod
    async def _bind_http_api(
        account_id: str,
        provider_id: str,
        gateways: list[Gateway],
        endpoint_ids_by_key: dict[tuple[Chain, Network, EndpointProtocol], list[str]],
        *,
        using_db: BaseDBAsyncClient,
    ) -> RouteBindingStats:
        stats = RouteBindingStats()
        for gateway in gateways:
            endpoint_ids = endpoint_ids_by_key.get(
                (Chain(gateway.chain), Network(gateway.network), EndpointProtocol.HTTP_API),
                [],
            )
            if not endpoint_ids:
                continue
            route = await HttpApiRoute.select_for_update(using_db=using_db).get_or_none(
                gateway_id=gateway.id,
                deleted_at=None,
            )
            if route is None:
                continue
            targets = await (
                HttpApiRouteTarget.filter(route_id=route.id, deleted_at=None).using_db(using_db).order_by('position')
            )
            existing_ids = {target.endpoint_id for target in targets}
            additions = [endpoint_id for endpoint_id in endpoint_ids if endpoint_id not in existing_ids]
            capacity = max(0, _MAX_ROUTE_TARGETS - len(targets))
            accepted = additions[:capacity]
            skipped = len(additions) - len(accepted)
            if not accepted:
                stats = stats.merge(RouteBindingStats(skipped=skipped))
                continue
            strategy = HttpApiRoutingStrategyType(route.strategy_type)
            weight = 100 if strategy is HttpApiRoutingStrategyType.LOAD_BALANCE else None
            rows = [
                HttpApiRouteTarget(
                    route_id=route.id,
                    endpoint_id=endpoint_id,
                    source_provider_id=provider_id,
                    position=len(targets) + position,
                    weight=weight,
                )
                for position, endpoint_id in enumerate(accepted)
            ]
            await HttpApiRouteTarget.bulk_create(rows, using_db=using_db)
            await AppProviderManager._touch_http_api(account_id, route, using_db=using_db)
            stats = stats.merge(RouteBindingStats(added=len(rows), skipped=skipped))
        return stats

    @staticmethod
    async def _remove_jsonrpc_targets(
        account_id: str,
        route_id: str,
        target_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> int:
        route = await JsonRpcRoute.select_for_update(using_db=using_db).get(id=route_id)
        await JsonRpcRouteTarget.filter(id__in=target_ids).using_db(using_db).delete()
        targets = await JsonRpcRouteTarget.filter(route_id=route.id).using_db(using_db).order_by('position')
        for position, target in enumerate(targets):
            if target.position != position:
                await JsonRpcRouteTarget.filter(id=target.id).using_db(using_db).update(position=position)
        await AppProviderManager._touch_jsonrpc(account_id, route, using_db=using_db)
        return len(target_ids)

    @staticmethod
    async def _remove_http_targets(
        account_id: str,
        route_id: str,
        target_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> int:
        route = await HttpApiRoute.select_for_update(using_db=using_db).get(id=route_id)
        await HttpApiRouteTarget.filter(id__in=target_ids).using_db(using_db).delete()
        targets = await HttpApiRouteTarget.filter(route_id=route.id).using_db(using_db).order_by('position')
        for position, target in enumerate(targets):
            if target.position != position:
                await HttpApiRouteTarget.filter(id=target.id).using_db(using_db).update(position=position)
        await AppProviderManager._touch_http_api(account_id, route, using_db=using_db)
        return len(target_ids)

    @staticmethod
    async def _touch_jsonrpc(
        account_id: str,
        route: JsonRpcRoute,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        previous_version = route.version
        values = {
            'version': previous_version + 1,
            'modified_at': datetime_util.next_utc_timestamp(route.modified_at),
        }
        await JsonRpcRoute.filter(id=route.id).using_db(using_db).update(**values)
        route.update_from_dict(values)
        app_id = await AppProviderManager._jsonrpc_app_id(route, using_db)
        await write_audit_event(
            app_id,
            account_id=account_id,
            actor_id=account_id,
            resource_type='jsonrpc_route',
            resource_id=route.id,
            action=AppAuditAction.UPDATED,
            previous_version=previous_version,
            new_version=route.version,
            changed_fields=['targets'],
            using_db=using_db,
        )

    @staticmethod
    async def _touch_http_api(
        account_id: str,
        route: HttpApiRoute,
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        previous_version = route.version
        values = {
            'version': previous_version + 1,
            'modified_at': datetime_util.next_utc_timestamp(route.modified_at),
        }
        await HttpApiRoute.filter(id=route.id).using_db(using_db).update(**values)
        route.update_from_dict(values)
        gateway = await Gateway.filter(id=route.gateway_id).using_db(using_db).only('app_id').get()
        await write_audit_event(
            gateway.app_id,
            account_id=account_id,
            actor_id=account_id,
            resource_type='http_api_route',
            resource_id=route.id,
            action=AppAuditAction.UPDATED,
            previous_version=previous_version,
            new_version=route.version,
            changed_fields=['targets'],
            using_db=using_db,
        )

    @staticmethod
    async def _jsonrpc_app_id(route: JsonRpcRoute, using_db: BaseDBAsyncClient) -> str:
        gateway = await Gateway.filter(id=route.gateway_id).using_db(using_db).only('app_id').get()
        return gateway.app_id
