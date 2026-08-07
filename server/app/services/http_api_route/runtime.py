from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointDescriptor, EndpointProtocol, EndpointTrustLevel
from app.model.http_api_forwarding import HttpApiRoutePlan, HttpApiRouteTarget
from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.orm.http_api_route import HttpApiRoute
from app.orm.http_api_route import HttpApiRouteTarget as HttpApiRouteTargetRecord


class DatabaseHttpApiRoutePlanProvider:
    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
    ) -> HttpApiRoutePlan | None:
        route = await HttpApiRoute.filter(
            gateway_id=gateway_id,
            deleted_at=None,
            gateway__deleted_at=None,
            gateway__app__deleted_at=None,
            gateway__app__account_id=account_id,
        ).first()
        if route is None:
            return None
        rows = await (
            HttpApiRouteTargetRecord.filter(route_id=route.id, deleted_at=None, endpoint__deleted_at=None)
            .select_related('endpoint')
            .order_by('position')
        )
        strategy_type = HttpApiRoutingStrategyType(route.strategy_type)
        targets: list[HttpApiRouteTarget] = []
        for row in rows:
            if strategy_type is HttpApiRoutingStrategyType.LOAD_BALANCE:
                if row.weight is None or not 1 <= row.weight <= 1000:
                    raise ValueError('HTTP API load balance target weight is invalid.')
            elif row.weight is not None:
                raise ValueError('HTTP API priority failover target weight is invalid.')
            endpoint = row.endpoint
            descriptor = EndpointDescriptor(
                id=endpoint.id,
                account_id=endpoint.account_id,
                chain=Chain(endpoint.chain),
                network=Network(endpoint.network),
                protocol=EndpointProtocol(endpoint.protocol),
                enabled=endpoint.enabled,
                trust_level=EndpointTrustLevel(endpoint.trust_level),
                version=endpoint.version,
            )
            if descriptor.account_id != account_id or descriptor.chain is not chain or descriptor.network is not network:
                continue
            if descriptor.protocol is not EndpointProtocol.HTTP_API:
                continue
            targets.append(HttpApiRouteTarget(endpoint=descriptor, position=row.position, weight=row.weight))
        return HttpApiRoutePlan(
            id=route.id,
            account_id=account_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
            strategy_type=strategy_type,
            minimum_trust=EndpointTrustLevel(route.minimum_trust),
            max_latency_ms=route.max_latency_ms,
            max_attempts=route.max_attempts,
            retry_policy=HttpApiRetryPolicy(route.retry_policy),
            targets=tuple(targets),
        )
