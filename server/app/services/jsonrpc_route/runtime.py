from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointProtocol
from app.model.jsonrpc_forwarding import JsonRpcRoutePlan, JsonRpcRouteTarget
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType
from app.orm.jsonrpc_route import JsonRpcRouteScope
from app.orm.jsonrpc_route import JsonRpcRouteTarget as JsonRpcRouteTargetRecord

_DEFAULT_METHOD = ''


class DatabaseJsonRpcRoutePlanProvider:
    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
        method: str,
    ) -> JsonRpcRoutePlan | None:
        scope = await self._get_scope(account_id, gateway_id, method)
        if scope is None:
            scope = await self._get_scope(account_id, gateway_id, _DEFAULT_METHOD)
        if scope is None:
            return None
        route = scope.route
        rows = await (
            JsonRpcRouteTargetRecord.filter(route_id=route.id, deleted_at=None, endpoint__deleted_at=None)
            .select_related('endpoint')
            .order_by('position')
        )
        strategy_type = JsonRpcRoutingStrategyType(route.strategy_type)
        targets: list[JsonRpcRouteTarget] = []
        for row in rows:
            endpoint = row.endpoint
            match strategy_type:
                case JsonRpcRoutingStrategyType.LOAD_BALANCE:
                    if row.weight is None or not 1 <= row.weight <= 1000:
                        raise ValueError('JSON-RPC load balance target weight is invalid.')
                case JsonRpcRoutingStrategyType.PRIORITY_FAILOVER:
                    if row.weight is not None:
                        raise ValueError('JSON-RPC priority failover target weight is invalid.')
                case _:
                    raise ValueError('JSON-RPC route strategy type is invalid.')
            descriptor = EndpointDescriptor(
                id=endpoint.id,
                account_id=endpoint.account_id,
                chain=Chain(endpoint.chain),
                network=Network(endpoint.network),
                protocol=EndpointProtocol(endpoint.protocol),
                enabled=endpoint.enabled,
                version=endpoint.version,
            )
            if descriptor.account_id != account_id or descriptor.chain is not chain or descriptor.network is not network:
                continue
            if descriptor.protocol is not EndpointProtocol.JSONRPC:
                continue
            targets.append(JsonRpcRouteTarget(endpoint=descriptor, position=row.position, weight=row.weight))
        return JsonRpcRoutePlan(
            id=route.id,
            account_id=account_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
            strategy_type=strategy_type,
            max_attempts=route.max_attempts,
            retry_policy=JsonRpcRetryPolicy(route.retry_policy),
            targets=tuple(targets),
        )

    @staticmethod
    async def _get_scope(account_id: str, gateway_id: str, method: str) -> JsonRpcRouteScope | None:
        return await (
            JsonRpcRouteScope.filter(
                gateway_id=gateway_id,
                method=method,
                deleted_at=None,
                route__deleted_at=None,
                gateway__deleted_at=None,
                gateway__app__deleted_at=None,
                gateway__app__account_id=account_id,
            )
            .select_related('route')
            .first()
        )
