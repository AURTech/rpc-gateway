from fastlog import log
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError

from app.core.config import CONF
from app.core.errors import BadRequestError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.application import AppAuditAction
from app.model.endpoint import EndpointProtocol
from app.model.jsonrpc_route import (
    CreateJsonRpcMethodRouteParams,
    JsonRpcLoadBalanceItem,
    JsonRpcLoadBalanceParams,
    JsonRpcLoadBalanceTargetItem,
    JsonRpcMethodRouteList,
    JsonRpcPriorityFailoverItem,
    JsonRpcPriorityFailoverParams,
    JsonRpcPriorityFailoverTargetItem,
    JsonRpcRouteItem,
    JsonRpcRouteValues,
    JsonRpcRoutingStrategyType,
    ReplaceJsonRpcMethodRouteParams,
    ReplaceJsonRpcRouteParams,
)
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteScope, JsonRpcRouteTarget
from app.services.application.audit import write_audit_event
from app.util import datetime as datetime_util

_DEFAULT_METHOD = ''


class JsonRpcRouteManager:
    @staticmethod
    async def get_default(account_id: str, gateway_id: str) -> JsonRpcRouteItem:
        gateway = await JsonRpcRouteManager._get_gateway(account_id, gateway_id)
        route = await JsonRpcRouteManager._get_scoped_route(gateway.id, _DEFAULT_METHOD)
        return await JsonRpcRouteManager._to_item(route)

    @staticmethod
    async def replace_default(
        account_id: str,
        actor_id: str,
        gateway_id: str,
        params: ReplaceJsonRpcRouteParams,
    ) -> JsonRpcRouteItem:
        gateway = await JsonRpcRouteManager._get_gateway(account_id, gateway_id)
        async with in_tx() as connection:
            route = await JsonRpcRouteManager._lock_scoped_route(gateway.id, _DEFAULT_METHOD, using_db=connection)
            await JsonRpcRouteManager._replace_route(
                route,
                gateway,
                account_id=account_id,
                actor_id=actor_id,
                params=params,
                methods=[_DEFAULT_METHOD],
                using_db=connection,
            )
        log.info(f'RPC default route updated | Account:{account_id} | Gateway:{gateway.id} | Version:{route.version}')
        return await JsonRpcRouteManager._to_item(route)

    @staticmethod
    async def list_methods(account_id: str, gateway_id: str) -> JsonRpcMethodRouteList:
        gateway = await JsonRpcRouteManager._get_gateway(account_id, gateway_id)
        scopes = await JsonRpcRouteScope.filter(gateway_id=gateway.id, deleted_at=None).exclude(method=_DEFAULT_METHOD)
        route_ids = list(dict.fromkeys(scope.route_id for scope in scopes))
        routes = await JsonRpcRoute.filter(id__in=route_ids, deleted_at=None).order_by('created_at', 'id')
        items = [await JsonRpcRouteManager._to_item(route) for route in routes]
        return JsonRpcMethodRouteList(total=len(items), items=items)

    @staticmethod
    async def create_method(
        account_id: str,
        actor_id: str,
        gateway_id: str,
        params: CreateJsonRpcMethodRouteParams,
    ) -> JsonRpcRouteItem:
        gateway = await JsonRpcRouteManager._get_gateway(account_id, gateway_id)
        JsonRpcRouteManager._validate_attempts(params)
        try:
            async with in_tx() as connection:
                endpoints = await JsonRpcRouteManager._validate_targets(account_id, gateway, params, using_db=connection)
                route = await JsonRpcRoute.create(
                    using_db=connection,
                    gateway_id=gateway.id,
                    **JsonRpcRouteManager._route_values(params),
                )
                await JsonRpcRouteManager._save_scopes(route.id, gateway.id, params.methods, using_db=connection)
                await JsonRpcRouteManager._save_targets(route.id, endpoints, params, using_db=connection)
                await write_audit_event(
                    gateway.app_id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='jsonrpc_route',
                    resource_id=route.id,
                    action=AppAuditAction.CREATED,
                    previous_version=None,
                    new_version=1,
                    changed_fields=['methods', 'policy', 'strategy', 'targets'],
                    using_db=connection,
                )
        except IntegrityError as exc:
            raise BadRequestError('One or more JSON-RPC methods already have a route.') from exc
        log.info(f'JSON-RPC method route created | Account:{account_id} | Gateway:{gateway.id} | Route:{route.id}')
        return await JsonRpcRouteManager._to_item(route)

    @staticmethod
    async def replace_method(
        account_id: str,
        actor_id: str,
        gateway_id: str,
        route_id: str,
        params: ReplaceJsonRpcMethodRouteParams,
    ) -> JsonRpcRouteItem:
        gateway = await JsonRpcRouteManager._get_gateway(account_id, gateway_id)
        try:
            async with in_tx() as connection:
                route = await JsonRpcRouteManager._lock_method_route(gateway.id, route_id, using_db=connection)
                await JsonRpcRouteManager._replace_route(
                    route,
                    gateway,
                    account_id=account_id,
                    actor_id=actor_id,
                    params=params,
                    methods=params.methods,
                    using_db=connection,
                )
        except IntegrityError as exc:
            raise BadRequestError('One or more JSON-RPC methods already have a route.') from exc
        log.info(f'JSON-RPC method route updated | Account:{account_id} | Gateway:{gateway.id} | Route:{route.id}')
        return await JsonRpcRouteManager._to_item(route)

    @staticmethod
    async def delete_method(
        account_id: str,
        actor_id: str,
        gateway_id: str,
        route_id: str,
        expected_version: int,
    ) -> JsonRpcRouteItem:
        gateway = await JsonRpcRouteManager._get_gateway(account_id, gateway_id)
        async with in_tx() as connection:
            route = await JsonRpcRouteManager._lock_method_route(gateway.id, route_id, using_db=connection)
            if route.version != expected_version:
                raise BadRequestError('JSON-RPC route version conflict. Reload the route before saving.')
            item = await JsonRpcRouteManager._to_item(route, using_db=connection)
            await write_audit_event(
                gateway.app_id,
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
        log.info(f'JSON-RPC method route deleted | Account:{account_id} | Gateway:{gateway.id} | Route:{route.id}')
        return item

    @staticmethod
    async def _replace_route(
        route: JsonRpcRoute,
        gateway: Gateway,
        *,
        account_id: str,
        actor_id: str,
        params: ReplaceJsonRpcRouteParams | ReplaceJsonRpcMethodRouteParams,
        methods: list[str],
        using_db: BaseDBAsyncClient,
    ) -> None:
        if route.version != params.expected_version:
            raise BadRequestError('JSON-RPC route version conflict. Reload the route before saving.')
        JsonRpcRouteManager._validate_attempts(params)
        endpoints = await JsonRpcRouteManager._validate_targets(account_id, gateway, params, using_db=using_db)
        previous_version = route.version
        values = JsonRpcRouteManager._route_values(params)
        values['version'] = previous_version + 1
        values['modified_at'] = datetime_util.next_utc_timestamp(route.modified_at)
        await JsonRpcRoute.filter(id=route.id).using_db(using_db).update(**values)
        route.update_from_dict(values)
        old_targets = (
            await JsonRpcRouteTarget.filter(route_id=route.id)
            .using_db(using_db)
            .only(
                'endpoint_id',
                'source_provider_id',
            )
        )
        source_provider_by_endpoint = {
            target.endpoint_id: target.source_provider_id for target in old_targets if target.source_provider_id is not None
        }
        await JsonRpcRouteScope.filter(route_id=route.id).using_db(using_db).delete()
        await JsonRpcRouteTarget.filter(route_id=route.id).using_db(using_db).delete()
        await JsonRpcRouteManager._save_scopes(route.id, gateway.id, methods, using_db=using_db)
        await JsonRpcRouteManager._save_targets(
            route.id,
            endpoints,
            params,
            source_provider_by_endpoint=source_provider_by_endpoint,
            using_db=using_db,
        )
        await write_audit_event(
            gateway.app_id,
            account_id=account_id,
            actor_id=actor_id,
            resource_type='jsonrpc_route',
            resource_id=route.id,
            action=AppAuditAction.UPDATED,
            previous_version=previous_version,
            new_version=route.version,
            changed_fields=['methods', 'policy', 'strategy', 'targets'],
            using_db=using_db,
        )

    @staticmethod
    def _validate_attempts(params: JsonRpcRouteValues) -> None:
        if params.max_attempts > CONF.JSONRPC_FORWARDING_MAX_ATTEMPTS:
            raise BadRequestError('JSON-RPC route attempts exceed the deployment limit.')

    @staticmethod
    async def _validate_targets(
        account_id: str,
        gateway: Gateway,
        params: JsonRpcRouteValues,
        *,
        using_db: BaseDBAsyncClient,
    ) -> list[Endpoint]:
        endpoint_ids = [target.endpoint_id for target in params.strategy.targets]
        if not endpoint_ids:
            return []
        rows = await (
            Endpoint.select_for_update(using_db=using_db)
            .filter(id__in=endpoint_ids, account_id=account_id, deleted_at=None)
            .order_by('id')
        )
        endpoints = {endpoint.id: endpoint for endpoint in rows}
        if set(endpoint_ids) != set(endpoints):
            raise BadRequestError('One or more JSON-RPC route Endpoints are unavailable.')
        ordered = [endpoints[endpoint_id] for endpoint_id in endpoint_ids]
        invalid = any(
            endpoint.chain != gateway.chain
            or endpoint.network != gateway.network
            or EndpointProtocol(endpoint.protocol) is not EndpointProtocol.JSONRPC
            for endpoint in ordered
        )
        if invalid:
            raise BadRequestError('JSON-RPC route Endpoints must match the Gateway chain, network, and protocol.')
        return ordered

    @staticmethod
    def _route_values(params: JsonRpcRouteValues) -> dict[str, object]:
        return {
            'strategy_type': params.strategy.type,
            'minimum_trust': params.minimum_trust,
            'max_latency_ms': params.max_latency_ms,
            'max_attempts': params.max_attempts,
            'retry_policy': params.retry_policy,
        }

    @staticmethod
    async def _save_scopes(
        route_id: str,
        gateway_id: str,
        methods: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        rows = [JsonRpcRouteScope(route_id=route_id, gateway_id=gateway_id, method=method) for method in methods]
        await JsonRpcRouteScope.bulk_create(rows, using_db=using_db)

    @staticmethod
    async def _save_targets(
        route_id: str,
        endpoints: list[Endpoint],
        params: JsonRpcRouteValues,
        *,
        source_provider_by_endpoint: dict[str, str] | None = None,
        using_db: BaseDBAsyncClient,
    ) -> None:
        match params.strategy:
            case JsonRpcLoadBalanceParams():
                weights: dict[str, int | None] = {target.endpoint_id: target.weight for target in params.strategy.targets}
            case JsonRpcPriorityFailoverParams():
                weights = {target.endpoint_id: None for target in params.strategy.targets}
            case _:
                raise ValueError('JSON-RPC route strategy configuration is invalid.')
        providers = source_provider_by_endpoint or {}
        rows = [
            JsonRpcRouteTarget(
                route_id=route_id,
                endpoint_id=endpoint.id,
                source_provider_id=providers.get(endpoint.id),
                position=position,
                weight=weights[endpoint.id],
            )
            for position, endpoint in enumerate(endpoints)
        ]
        if rows:
            await JsonRpcRouteTarget.bulk_create(rows, using_db=using_db)

    @staticmethod
    async def _get_gateway(account_id: str, gateway_id: str) -> Gateway:
        gateway = await (
            Gateway.filter(id=gateway_id, app__account_id=account_id, app__deleted_at=None, deleted_at=None)
            .select_related('app')
            .first()
        )
        if gateway is None:
            raise NotfoundError('Gateway not found.')
        return gateway

    @staticmethod
    async def _get_scoped_route(gateway_id: str, method: str) -> JsonRpcRoute:
        scope = await (
            JsonRpcRouteScope.filter(gateway_id=gateway_id, method=method, deleted_at=None, route__deleted_at=None)
            .select_related('route')
            .first()
        )
        if scope is None:
            raise NotfoundError('JSON-RPC route not found.')
        return scope.route

    @staticmethod
    async def _lock_scoped_route(
        gateway_id: str,
        method: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> JsonRpcRoute:
        scope = await JsonRpcRouteScope.filter(gateway_id=gateway_id, method=method, deleted_at=None).using_db(using_db).first()
        if scope is None:
            raise NotfoundError('JSON-RPC route not found.')
        route = await JsonRpcRoute.select_for_update(using_db=using_db).get_or_none(id=scope.route_id, deleted_at=None)
        if route is None:
            raise NotfoundError('JSON-RPC route not found.')
        return route

    @staticmethod
    async def _lock_method_route(
        gateway_id: str,
        route_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> JsonRpcRoute:
        route = await JsonRpcRoute.select_for_update(using_db=using_db).get_or_none(
            id=route_id,
            gateway_id=gateway_id,
            deleted_at=None,
        )
        if route is None:
            raise NotfoundError('JSON-RPC method route not found.')
        default_scope = await JsonRpcRouteScope.filter(route_id=route.id, method=_DEFAULT_METHOD).using_db(using_db).exists()
        if default_scope:
            raise NotfoundError('JSON-RPC method route not found.')
        return route

    @staticmethod
    async def _to_item(route: JsonRpcRoute, *, using_db: BaseDBAsyncClient | None = None) -> JsonRpcRouteItem:
        scope_query = JsonRpcRouteScope.filter(route_id=route.id, deleted_at=None).order_by('method')
        target_query = JsonRpcRouteTarget.filter(route_id=route.id, deleted_at=None).order_by('position')
        if using_db is not None:
            scope_query = scope_query.using_db(using_db)
            target_query = target_query.using_db(using_db)
        scopes = await scope_query
        targets = await target_query
        methods = [scope.method for scope in scopes if scope.method]
        is_default = any(not scope.method for scope in scopes)
        try:
            strategy_type = JsonRpcRoutingStrategyType(route.strategy_type)
            match strategy_type:
                case JsonRpcRoutingStrategyType.LOAD_BALANCE:
                    if any(target.weight is None or not 1 <= target.weight <= 1000 for target in targets):
                        raise ValueError('JSON-RPC load balance target weight is invalid.')
                    strategy = JsonRpcLoadBalanceItem(
                        targets=[
                            JsonRpcLoadBalanceTargetItem(
                                endpoint_id=target.endpoint_id,
                                position=target.position,
                                weight=target.weight,
                            )
                            for target in targets
                            if target.weight is not None
                        ],
                    )
                case JsonRpcRoutingStrategyType.PRIORITY_FAILOVER:
                    if any(target.weight is not None for target in targets):
                        raise ValueError('JSON-RPC priority failover target weight is invalid.')
                    strategy = JsonRpcPriorityFailoverItem(
                        targets=[
                            JsonRpcPriorityFailoverTargetItem(
                                endpoint_id=target.endpoint_id,
                                position=target.position,
                            )
                            for target in targets
                        ],
                    )
                case _:
                    raise ValueError('JSON-RPC route strategy type is invalid.')
            return JsonRpcRouteItem(
                id=route.id,
                gateway_id=route.gateway_id,
                methods=methods,
                is_default=is_default,
                minimum_trust=route.minimum_trust,
                max_latency_ms=route.max_latency_ms,
                max_attempts=route.max_attempts,
                retry_policy=route.retry_policy,
                strategy=strategy,
                version=route.version,
                created_at=route.created_at,
                modified_at=route.modified_at,
            )
        except ValueError as exc:
            raise UnavailableError('JSON-RPC route configuration is unavailable.') from exc
