from datetime import UTC, datetime, timedelta
from typing import Any

from app.model.blockchain import Chain, Network
from app.model.usage import GatewayUsageEvent
from app.orm.gateway import Gateway
from app.orm.usage import GatewayUsageHourly, GatewayUsageMethodHourly
from app.util.datetime import floor_utc_hour


def make_event(event_id: str, method: str = 'eth_call', *, successful: bool = True) -> GatewayUsageEvent:
    return GatewayUsageEvent(
        event_id=event_id,
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method=method,
        started_at=datetime.now(UTC),
        successful=successful,
        duration_ms=10,
        request_bytes=2,
        response_bytes=8,
        cache_eligible=True,
        cache_hit=successful,
    )


async def create_gateway(
    app_id: str,
    *,
    chain: Chain,
    network: Network = Network.MAINNET,
    name: str | None = None,
) -> Gateway:
    return await Gateway.create(
        app_id=app_id,
        name=name or f'{chain.value}-{network.value}',
        chain=chain,
        network=network,
        transport_types=['jsonrpc'],
    )


async def create_hourly_usage(
    account_id: str,
    app_id: str,
    gateway: Gateway,
    *,
    total_requests: int,
    methods: dict[str, int] | None = None,
    method_cache: dict[str, tuple[int, int]] | None = None,
) -> None:
    """Write one hourly gateway bucket, plus one method bucket per entry in ``methods``."""
    bucket_hour = floor_utc_hour(datetime.now(UTC) - timedelta(hours=1))
    cache = method_cache or {}
    await GatewayUsageHourly.create(
        account_id=account_id,
        app_id=app_id,
        gateway_id=gateway.id,
        chain=gateway.chain,
        network=gateway.network,
        bucket_hour=bucket_hour,
        total_requests=total_requests,
        successful_requests=total_requests,
        total_duration_ms=total_requests * 10,
        cache_eligible_requests=sum(eligible for eligible, _hits in cache.values()),
        cache_hit_requests=sum(hits for _eligible, hits in cache.values()),
    )
    if not methods:
        return
    await GatewayUsageMethodHourly.bulk_create(
        [
            GatewayUsageMethodHourly(
                account_id=account_id,
                app_id=app_id,
                gateway_id=gateway.id,
                chain=gateway.chain,
                network=gateway.network,
                method=method,
                bucket_hour=bucket_hour,
                total_requests=requests,
                successful_requests=requests,
                total_duration_ms=requests * 10,
                cache_eligible_requests=cache.get(method, (0, 0))[0],
                cache_hit_requests=cache.get(method, (0, 0))[1],
            )
            for method, requests in methods.items()
        ]
    )


def point_total(item: dict[str, Any]) -> int:
    points = item['points']
    assert isinstance(points, list)
    return sum(int(point['total_requests']) for point in points)
