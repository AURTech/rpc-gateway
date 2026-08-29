from fastlog import log
from tortoise.backends.base.client import BaseDBAsyncClient

from app.core.config import CONF
from app.core.errors import BadRequestError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.application import AppAuditAction
from app.model.endpoint import EndpointProtocol
from app.model.http_api_route import (
    HttpApiLoadBalanceItem,
    HttpApiLoadBalanceParams,
    HttpApiLoadBalanceTargetItem,
    HttpApiPriorityFailoverItem,
    HttpApiPriorityFailoverParams,
    HttpApiPriorityFailoverTargetItem,
    HttpApiRouteItem,
    HttpApiRouteValues,
    HttpApiRoutingStrategyType,
    ReplaceHttpApiRouteParams,
)
from app.model.transport import Transport
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.http_api_route import HttpApiRoute, HttpApiRouteTarget
from app.services.application.audit import write_audit_event
from app.util import datetime as datetime_util


class HttpApiRouteManager:
    @staticmethod
    async def get(account_id: str, gateway_id: str) -> HttpApiRouteItem:
        gateway = await HttpApiRouteManager._get_gateway(account_id, gateway_id)
        route = await HttpApiRoute.get_or_none(gateway_id=gateway.id, deleted_at=None)
        if route is None:
            raise NotfoundError('HTTP API route not found.')
        return await HttpApiRouteManager._to_item(route)

    @staticmethod
    async def replace(
        account_id: str,
        actor_id: str,
        gateway_id: str,
        params: ReplaceHttpApiRouteParams,
    ) -> HttpApiRouteItem:
        gateway = await HttpApiRouteManager._get_gateway(account_id, gateway_id)
        if params.max_attempts > CONF.HTTP_API_FORWARDING_MAX_ATTEMPTS:
            raise BadRequestError('HTTP API route attempts exceed the deployment limit.')
        async with in_tx() as connection:
            route = await HttpApiRoute.select_for_update(using_db=connection).get_or_none(
                gateway_id=gateway.id, deleted_at=None
            )
            if route is None:
                raise NotfoundError('HTTP API route not found.')
            if route.version != params.expected_version:
                raise BadRequestError('HTTP API route version conflict. Reload the route before saving.')
            endpoints = await HttpApiRouteManager._validate_targets(account_id, gateway, params, using_db=connection)
            previous_version = route.version
            values = HttpApiRouteManager._route_values(params)
            values['version'] = previous_version + 1
            values['modified_at'] = datetime_util.next_utc_timestamp(route.modified_at)
            await HttpApiRoute.filter(id=route.id).using_db(connection).update(**values)
            route.update_from_dict(values)
            old_targets = (
                await HttpApiRouteTarget.filter(route_id=route.id)
                .using_db(connection)
                .only(
                    'endpoint_id',
                    'source_provider_id',
                )
            )
            source_provider_by_endpoint = {
                target.endpoint_id: target.source_provider_id for target in old_targets if target.source_provider_id is not None
            }
            await HttpApiRouteTarget.filter(route_id=route.id).using_db(connection).delete()
            await HttpApiRouteManager._save_targets(
                route.id,
                endpoints,
                params,
                source_provider_by_endpoint=source_provider_by_endpoint,
                using_db=connection,
            )
            await write_audit_event(
                gateway.app_id,
                account_id=account_id,
                actor_id=actor_id,
                resource_type='http_api_route',
                resource_id=route.id,
                action=AppAuditAction.UPDATED,
                previous_version=previous_version,
                new_version=route.version,
                changed_fields=['policy', 'strategy', 'targets'],
                using_db=connection,
            )
        log.info(f'HTTP API route updated | Account:{account_id} | Gateway:{gateway.id} | Version:{route.version}')
        return await HttpApiRouteManager._to_item(route)

    @staticmethod
    async def _get_gateway(account_id: str, gateway_id: str) -> Gateway:
        gateway = await (
            Gateway.filter(id=gateway_id, app__account_id=account_id, app__deleted_at=None, deleted_at=None)
            .select_related('app')
            .first()
        )
        if gateway is None:
            raise NotfoundError('Gateway not found.')
        if Transport.HTTP_API.value not in gateway.transport_types:
            raise NotfoundError('HTTP API route not found.')
        return gateway

    @staticmethod
    async def _validate_targets(
        account_id: str,
        gateway: Gateway,
        params: HttpApiRouteValues,
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
            raise BadRequestError('One or more HTTP API route Endpoints are unavailable.')
        ordered = [endpoints[endpoint_id] for endpoint_id in endpoint_ids]
        invalid = any(
            endpoint.chain != gateway.chain
            or endpoint.network != gateway.network
            or EndpointProtocol(endpoint.protocol) is not EndpointProtocol.HTTP_API
            for endpoint in ordered
        )
        if invalid:
            raise BadRequestError('HTTP API route Endpoints must match the Gateway chain, network, and protocol.')
        return ordered

    @staticmethod
    def _route_values(params: HttpApiRouteValues) -> dict[str, object]:
        return {
            'strategy_type': params.strategy.type,
            'max_attempts': params.max_attempts,
            'retry_policy': params.retry_policy,
        }

    @staticmethod
    async def _save_targets(
        route_id: str,
        endpoints: list[Endpoint],
        params: HttpApiRouteValues,
        *,
        source_provider_by_endpoint: dict[str, str] | None = None,
        using_db: BaseDBAsyncClient,
    ) -> None:
        match params.strategy:
            case HttpApiLoadBalanceParams():
                weights: dict[str, int | None] = {target.endpoint_id: target.weight for target in params.strategy.targets}
            case HttpApiPriorityFailoverParams():
                weights = {target.endpoint_id: None for target in params.strategy.targets}
            case _:
                raise ValueError('HTTP API route strategy configuration is invalid.')
        providers = source_provider_by_endpoint or {}
        rows = [
            HttpApiRouteTarget(
                route_id=route_id,
                endpoint_id=endpoint.id,
                source_provider_id=providers.get(endpoint.id),
                position=position,
                weight=weights[endpoint.id],
            )
            for position, endpoint in enumerate(endpoints)
        ]
        if rows:
            await HttpApiRouteTarget.bulk_create(rows, using_db=using_db)

    @staticmethod
    async def _to_item(route: HttpApiRoute) -> HttpApiRouteItem:
        targets = await HttpApiRouteTarget.filter(route_id=route.id, deleted_at=None).order_by('position')
        try:
            strategy_type = HttpApiRoutingStrategyType(route.strategy_type)
            if strategy_type is HttpApiRoutingStrategyType.LOAD_BALANCE:
                if any(target.weight is None or not 1 <= target.weight <= 1000 for target in targets):
                    raise ValueError('HTTP API load balance target weight is invalid.')
                strategy = HttpApiLoadBalanceItem(
                    targets=[
                        HttpApiLoadBalanceTargetItem(
                            endpoint_id=target.endpoint_id, position=target.position, weight=target.weight
                        )
                        for target in targets
                        if target.weight is not None
                    ]
                )
            else:
                if any(target.weight is not None for target in targets):
                    raise ValueError('HTTP API priority failover target weight is invalid.')
                strategy = HttpApiPriorityFailoverItem(
                    targets=[
                        HttpApiPriorityFailoverTargetItem(endpoint_id=target.endpoint_id, position=target.position)
                        for target in targets
                    ]
                )
            return HttpApiRouteItem(
                id=route.id,
                gateway_id=route.gateway_id,
                max_attempts=route.max_attempts,
                retry_policy=route.retry_policy,
                strategy=strategy,
                version=route.version,
                created_at=route.created_at,
                modified_at=route.modified_at,
            )
        except ValueError as exc:
            raise UnavailableError('HTTP API route configuration is unavailable.') from exc
