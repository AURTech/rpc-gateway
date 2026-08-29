from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from tortoise.functions import Sum
from tortoise.queryset import QuerySet

from app.core.errors import InternalError, NotfoundError
from app.model.blockchain import CHAIN_CATALOG, Chain, Network
from app.model.usage import (
    UsageByEndpoint,
    UsageByMethod,
    UsageByMethodItem,
    UsageByNetwork,
    UsageByNetworkItem,
    UsageByRoute,
    UsageEndpointItem,
    UsageEndpointPoint,
    UsageGranularity,
    UsageMethodPoint,
    UsageMethodRank,
    UsageMetrics,
    UsageNetworkPoint,
    UsagePreviousWindow,
    UsageRange,
    UsageRouteItem,
    UsageRouteMetrics,
    UsageRoutePoint,
    UsageSeries,
    UsageSeriesPoint,
    UsageWindow,
)
from app.orm.application import App
from app.orm.endpoint import Endpoint
from app.orm.functions import DateTrunc
from app.orm.gateway import Gateway
from app.orm.http_api_route import HttpApiRoute
from app.orm.jsonrpc_route import JsonRpcRoute
from app.orm.usage import (
    GatewayUsageEndpointFiveMinute,
    GatewayUsageEndpointHourly,
    GatewayUsageFiveMinute,
    GatewayUsageHourly,
    GatewayUsageMethodFiveMinute,
    GatewayUsageMethodHourly,
    GatewayUsageMetricAvailability,
    GatewayUsageRouteFiveMinute,
    GatewayUsageRouteHourly,
)
from app.util.datetime import floor_utc_five_minutes, floor_utc_hour

_FIELDS = (
    'total_requests',
    'successful_requests',
    'failed_requests',
    'total_duration_ms',
    'total_request_bytes',
    'total_response_bytes',
    'cache_eligible_requests',
    'cache_hit_requests',
)
_METRIC_FIELDS = tuple(f'metric_{field}' for field in _FIELDS)
_METHOD_FIELDS = ('total_requests', 'cache_eligible_requests', 'cache_hit_requests')
_METHOD_METRIC_FIELDS = tuple(f'metric_{field}' for field in _METHOD_FIELDS)
_NETWORK_FIELDS = ('total_requests', 'total_duration_ms', 'cache_eligible_requests', 'cache_hit_requests')
_NETWORK_METRIC_FIELDS = tuple(f'metric_{field}' for field in _NETWORK_FIELDS)
_ENDPOINT_DB_FIELDS = ('total_attempts', 'first_attempts', 'retry_attempts')
_ENDPOINT_FIELDS = (*_ENDPOINT_DB_FIELDS, 'unclassified_attempts')
_ENDPOINT_METRIC_FIELDS = tuple(f'metric_{field}' for field in _ENDPOINT_DB_FIELDS)
_ROUTE_USAGE_METRIC = 'route_usage'
_ENDPOINT_CLASSIFICATION_METRIC = 'endpoint_attempt_classification'
_ROUTE_FIELDS = (
    'routed_requests',
    'successful_requests',
    'failed_requests',
    'total_duration_ms',
    'total_attempts',
    'multi_attempt_requests',
    'exhausted_requests',
)
_ROUTE_METRIC_FIELDS = tuple(f'metric_{field}' for field in _ROUTE_FIELDS)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Window:
    start_at: datetime
    end_at: datetime
    width: timedelta
    granularity: UsageGranularity


def _usage_window(time_range: UsageRange, now: datetime | None = None) -> _Window:
    value = (now or datetime.now(UTC)).astimezone(UTC)
    if time_range is UsageRange.HOURLY:
        end = floor_utc_five_minutes(value)
        return _Window(
            start_at=end - timedelta(hours=1),
            end_at=end,
            width=timedelta(minutes=5),
            granularity=UsageGranularity.FIVE_MINUTE,
        )
    if time_range is UsageRange.DAILY:
        end = floor_utc_hour(value)
        return _Window(
            start_at=end - timedelta(days=1),
            end_at=end,
            width=timedelta(hours=1),
            granularity=UsageGranularity.HOURLY,
        )
    end = value.replace(hour=0, minute=0, second=0, microsecond=0)
    days = 7 if time_range is UsageRange.WEEKLY else 30
    return _Window(
        start_at=end - timedelta(days=days),
        end_at=end,
        width=timedelta(days=1),
        granularity=UsageGranularity.DAILY,
    )


# The comparison window for a summary: the same span shifted back so it ends
# exactly where the reported window starts. Granularity is kept so the previous
# window reads from the same table (fine 5-minute rows vs. hourly rollups).
def _previous_window(window: _Window) -> _Window:
    span = window.end_at - window.start_at
    return _Window(
        start_at=window.start_at - span,
        end_at=window.start_at,
        width=window.width,
        granularity=window.granularity,
    )


def _empty_values(fields: tuple[str, ...] = _FIELDS) -> dict[str, int]:
    return dict.fromkeys(fields, 0)


def _db_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int | str | bytes | bytearray | Decimal):
        return int(value)
    raise InternalError('Invalid usage aggregate value.')


def _db_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise InternalError('Invalid usage bucket value.')
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _row_values(row: dict[str, Any], fields: tuple[str, ...] = _FIELDS) -> dict[str, int]:
    values: dict[str, int] = {}
    for field in fields:
        value = row.get(f'metric_{field}', row.get(field))
        values[field] = _db_int(value)
    return values


def _endpoint_values(row: dict[str, Any]) -> dict[str, int]:
    values = _row_values(row, _ENDPOINT_DB_FIELDS)
    classified = values['first_attempts'] + values['retry_attempts']
    values['unclassified_attempts'] = values['total_attempts'] - classified
    return values


def _metrics(values: dict[str, int]) -> UsageMetrics:
    total = values['total_requests']
    eligible = values['cache_eligible_requests']
    traffic = values['total_request_bytes'] + values['total_response_bytes']
    return UsageMetrics(
        **values,
        success_rate=values['successful_requests'] / total if total else 0,
        avg_duration_ms=values['total_duration_ms'] / total if total else 0,
        total_traffic_bytes=traffic,
        cache_hit_rate=values['cache_hit_requests'] / eligible if eligible else 0,
    )


def _metric_annotations(fields: tuple[str, ...] = _FIELDS) -> dict[str, Sum]:
    return {f'metric_{field}': Sum(field) for field in fields}


def _method_point(bucket_start: datetime, values: dict[str, int]) -> UsageMethodPoint:
    eligible = values['cache_eligible_requests']
    hit_rate = values['cache_hit_requests'] / eligible if eligible else 0
    return UsageMethodPoint(bucket_start=bucket_start, **values, cache_hit_rate=hit_rate)


def _network_point(bucket_start: datetime, values: dict[str, int]) -> UsageNetworkPoint:
    total = values['total_requests']
    eligible = values['cache_eligible_requests']
    return UsageNetworkPoint(
        bucket_start=bucket_start,
        **values,
        avg_duration_ms=values['total_duration_ms'] / total if total else 0,
        cache_hit_rate=values['cache_hit_requests'] / eligible if eligible else 0,
    )


def _route_metrics(values: dict[str, int]) -> UsageRouteMetrics:
    routed = values['routed_requests']
    failed = values['failed_requests']
    return UsageRouteMetrics(
        **values,
        success_rate=values['successful_requests'] / routed if routed else 0,
        avg_duration_ms=values['total_duration_ms'] / routed if routed else 0,
        avg_attempts=values['total_attempts'] / routed if routed else 0,
        multi_attempt_rate=values['multi_attempt_requests'] / routed if routed else 0,
        exhausted_rate=values['exhausted_requests'] / failed if failed else 0,
    )


def _route_point(bucket_start: datetime, values: dict[str, int]) -> UsageRoutePoint:
    return UsageRoutePoint(bucket_start=bucket_start, **_route_metrics(values).model_dump())


def _network_dimension(row: dict[str, Any]) -> tuple[Chain, Network]:
    try:
        chain = Chain(str(row['chain']))
        network = Network(str(row['network']))
        if network not in CHAIN_CATALOG[chain].networks:
            raise ValueError
    except (KeyError, ValueError) as exc:
        raise InternalError('Invalid usage network value.') from exc
    return chain, network


class GatewayUsageQueryManager:
    @staticmethod
    async def _coverage_start_at(metric: str) -> datetime | None:
        row = await GatewayUsageMetricAvailability.filter(metric=metric, deleted_at=None).first()
        if row is None:
            raise InternalError('Usage metric availability is missing.')
        return row.coverage_start_at.astimezone(UTC) if row.coverage_start_at is not None else None

    @staticmethod
    def _gateway_query(
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> QuerySet[GatewayUsageHourly]:
        query = GatewayUsageHourly.filter(
            account_id=account_id,
            bucket_hour__gte=window.start_at,
            bucket_hour__lt=window.end_at,
            deleted_at=None,
        )
        if app_id is not None:
            query = query.filter(app_id=app_id)
        if gateway_id is not None:
            query = query.filter(gateway_id=gateway_id)
        if chain is not None:
            query = query.filter(chain=chain)
        if network is not None:
            query = query.filter(network=network)
        return query

    @staticmethod
    def _method_query(
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> QuerySet[GatewayUsageMethodHourly]:
        query = GatewayUsageMethodHourly.filter(
            account_id=account_id,
            bucket_hour__gte=window.start_at,
            bucket_hour__lt=window.end_at,
            deleted_at=None,
        )
        if app_id is not None:
            query = query.filter(app_id=app_id)
        if gateway_id is not None:
            query = query.filter(gateway_id=gateway_id)
        if chain is not None:
            query = query.filter(chain=chain)
        if network is not None:
            query = query.filter(network=network)
        return query

    @staticmethod
    def _fine_gateway_query(
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> QuerySet[GatewayUsageFiveMinute]:
        query = GatewayUsageFiveMinute.filter(
            account_id=account_id,
            bucket_start__gte=window.start_at,
            bucket_start__lt=window.end_at,
            deleted_at=None,
        )
        if app_id is not None:
            query = query.filter(app_id=app_id)
        if gateway_id is not None:
            query = query.filter(gateway_id=gateway_id)
        if chain is not None:
            query = query.filter(chain=chain)
        if network is not None:
            query = query.filter(network=network)
        return query

    @staticmethod
    def _fine_method_query(
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> QuerySet[GatewayUsageMethodFiveMinute]:
        query = GatewayUsageMethodFiveMinute.filter(
            account_id=account_id,
            bucket_start__gte=window.start_at,
            bucket_start__lt=window.end_at,
            deleted_at=None,
        )
        if app_id is not None:
            query = query.filter(app_id=app_id)
        if gateway_id is not None:
            query = query.filter(gateway_id=gateway_id)
        if chain is not None:
            query = query.filter(chain=chain)
        if network is not None:
            query = query.filter(network=network)
        return query

    @classmethod
    async def _summary_row(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> dict[str, Any]:
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            query = cls._fine_gateway_query(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
        else:
            query = cls._gateway_query(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
        rows = await query.annotate(**_metric_annotations()).values(*_METRIC_FIELDS)
        return rows[0] if rows else {}

    @classmethod
    async def _series_rows(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> list[dict[str, Any]]:
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            query = cls._fine_gateway_query(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
            return await (
                query.annotate(**_metric_annotations())
                .group_by('bucket_start')
                .order_by('bucket_start')
                .values('bucket_start', *_METRIC_FIELDS)
            )
        query = cls._gateway_query(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
        )
        unit = 'day' if window.granularity is UsageGranularity.DAILY else 'hour'
        return await (
            query.annotate(bucket_start=DateTrunc('bucket_hour', unit), **_metric_annotations())
            .group_by('bucket_start')
            .order_by('bucket_start')
            .values('bucket_start', *_METRIC_FIELDS)
        )

    @classmethod
    async def _method_rows(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
        rank_by: UsageMethodRank,
        limit: int,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            query = cls._fine_method_query(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
            bucket_field = 'bucket_start'
        else:
            query = cls._method_query(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
            bucket_field = 'bucket_hour'
        rank_field = rank_by.value
        rank_query = query
        if rank_by is UsageMethodRank.CACHE_ELIGIBLE_REQUESTS:
            rank_query = rank_query.filter(cache_eligible_requests__gt=0)
        top_rows = await (
            rank_query.group_by('method')
            .annotate(rank_total=Sum(rank_field))
            .order_by('-rank_total', 'method')
            .limit(limit)
            .values('method', 'rank_total')
        )
        methods = [str(row['method']) for row in top_rows]
        if not methods:
            return [], []
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            rows = await (
                query.filter(method__in=methods)
                .annotate(**_metric_annotations(_METHOD_FIELDS))
                .group_by('method', bucket_field)
                .order_by('method', bucket_field)
                .values('method', bucket_field, *_METHOD_METRIC_FIELDS)
            )
            return methods, rows
        unit = 'day' if window.granularity is UsageGranularity.DAILY else 'hour'
        rows = await (
            query.filter(method__in=methods)
            .annotate(bucket_start=DateTrunc('bucket_hour', unit), **_metric_annotations(_METHOD_FIELDS))
            .group_by('method', 'bucket_start')
            .order_by('method', 'bucket_start')
            .values('method', 'bucket_start', *_METHOD_METRIC_FIELDS)
        )
        return methods, rows

    @classmethod
    async def _network_rows(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> list[dict[str, Any]]:
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            query = cls._fine_gateway_query(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
            return await (
                query.annotate(**_metric_annotations(_NETWORK_FIELDS))
                .group_by('chain', 'network', 'bucket_start')
                .order_by('chain', 'network', 'bucket_start')
                .values('chain', 'network', 'bucket_start', *_NETWORK_METRIC_FIELDS)
            )
        query = cls._gateway_query(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
        )
        unit = 'day' if window.granularity is UsageGranularity.DAILY else 'hour'
        return await (
            query.annotate(bucket_start=DateTrunc('bucket_hour', unit), **_metric_annotations(_NETWORK_FIELDS))
            .group_by('chain', 'network', 'bucket_start')
            .order_by('chain', 'network', 'bucket_start')
            .values('chain', 'network', 'bucket_start', *_NETWORK_METRIC_FIELDS)
        )

    @staticmethod
    async def _validate_endpoint_scope(
        account_id: str,
        *,
        app_id: str | None,
        gateway_id: str | None,
        route_id: str | None,
    ) -> None:
        if app_id is not None and not await App.filter(id=app_id, account_id=account_id, deleted_at=None).exists():
            raise NotfoundError('App not found.')
        if gateway_id is not None:
            gateway_query = Gateway.filter(
                id=gateway_id,
                deleted_at=None,
                app__deleted_at=None,
                app__account_id=account_id,
            )
            if app_id is not None:
                gateway_query = gateway_query.filter(app_id=app_id)
            if not await gateway_query.exists():
                raise NotfoundError('Gateway not found.')
        if route_id is None or gateway_id is None:
            return
        route_filters = {
            'id': route_id,
            'gateway_id': gateway_id,
            'deleted_at': None,
            'gateway__deleted_at': None,
            'gateway__app__deleted_at': None,
            'gateway__app__account_id': account_id,
        }
        if not await JsonRpcRoute.filter(**route_filters).exists() and not await HttpApiRoute.filter(**route_filters).exists():
            raise NotfoundError('Route not found.')

    @classmethod
    async def _endpoint_rows(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        route_id: str | None,
    ) -> list[dict[str, Any]]:
        await cls._validate_endpoint_scope(
            account_id,
            app_id=app_id,
            gateway_id=gateway_id,
            route_id=route_id,
        )
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            query = GatewayUsageEndpointFiveMinute.filter(
                account_id=account_id,
                bucket_start__gte=window.start_at,
                bucket_start__lt=window.end_at,
                deleted_at=None,
            )
            bucket_field = 'bucket_start'
        else:
            query = GatewayUsageEndpointHourly.filter(
                account_id=account_id,
                bucket_hour__gte=window.start_at,
                bucket_hour__lt=window.end_at,
                deleted_at=None,
            )
            bucket_field = 'bucket_hour'
        if app_id is not None:
            query = query.filter(app_id=app_id)
        if gateway_id is not None:
            query = query.filter(gateway_id=gateway_id)
        if route_id is not None:
            query = query.filter(route_id=route_id)
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            return await (
                query.annotate(**_metric_annotations(_ENDPOINT_DB_FIELDS))
                .group_by('endpoint_id', 'chain', 'network', bucket_field)
                .order_by('endpoint_id', bucket_field)
                .values('endpoint_id', 'chain', 'network', bucket_field, *_ENDPOINT_METRIC_FIELDS)
            )
        unit = 'day' if window.granularity is UsageGranularity.DAILY else 'hour'
        return await (
            query.annotate(bucket_start=DateTrunc('bucket_hour', unit), **_metric_annotations(_ENDPOINT_DB_FIELDS))
            .group_by('endpoint_id', 'chain', 'network', 'bucket_start')
            .order_by('endpoint_id', 'bucket_start')
            .values('endpoint_id', 'chain', 'network', 'bucket_start', *_ENDPOINT_METRIC_FIELDS)
        )

    @staticmethod
    async def _validate_route_scope(account_id: str, *, app_id: str, gateway_id: str | None) -> None:
        if not await App.filter(id=app_id, account_id=account_id, deleted_at=None).exists():
            raise NotfoundError('App not found.')
        if gateway_id is None:
            return
        if not await Gateway.filter(
            id=gateway_id,
            app_id=app_id,
            deleted_at=None,
            app__deleted_at=None,
            app__account_id=account_id,
        ).exists():
            raise NotfoundError('Gateway not found.')

    @classmethod
    async def _route_rows(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str,
        gateway_id: str | None,
        limit: int,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        await cls._validate_route_scope(account_id, app_id=app_id, gateway_id=gateway_id)
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            query = GatewayUsageRouteFiveMinute.filter(
                account_id=account_id,
                app_id=app_id,
                bucket_start__gte=window.start_at,
                bucket_start__lt=window.end_at,
                deleted_at=None,
            )
            bucket_field = 'bucket_start'
        else:
            query = GatewayUsageRouteHourly.filter(
                account_id=account_id,
                app_id=app_id,
                bucket_hour__gte=window.start_at,
                bucket_hour__lt=window.end_at,
                deleted_at=None,
            )
            bucket_field = 'bucket_hour'
        if gateway_id is not None:
            query = query.filter(gateway_id=gateway_id)
        top_rows = await (
            query.group_by('route_id')
            .annotate(rank_total=Sum('routed_requests'))
            .order_by('-rank_total', 'route_id')
            .limit(limit)
            .values('route_id', 'rank_total')
        )
        route_ids = [str(row['route_id']) for row in top_rows]
        if not route_ids:
            return [], []
        if window.granularity is UsageGranularity.FIVE_MINUTE:
            rows = await (
                query.filter(route_id__in=route_ids)
                .annotate(**_metric_annotations(_ROUTE_FIELDS))
                .group_by('route_id', 'gateway_id', 'chain', 'network', bucket_field)
                .order_by('route_id', bucket_field)
                .values('route_id', 'gateway_id', 'chain', 'network', bucket_field, *_ROUTE_METRIC_FIELDS)
            )
            return route_ids, rows
        unit = 'day' if window.granularity is UsageGranularity.DAILY else 'hour'
        rows = await (
            query.filter(route_id__in=route_ids)
            .annotate(bucket_start=DateTrunc('bucket_hour', unit), **_metric_annotations(_ROUTE_FIELDS))
            .group_by('route_id', 'gateway_id', 'chain', 'network', 'bucket_start')
            .order_by('route_id', 'bucket_start')
            .values('route_id', 'gateway_id', 'chain', 'network', 'bucket_start', *_ROUTE_METRIC_FIELDS)
        )
        return route_ids, rows

    @classmethod
    async def get_summary(
        cls,
        account_id: str,
        *,
        time_range: UsageRange,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
        compare: bool = False,
    ) -> UsageWindow:
        window = _usage_window(time_range)
        row = await cls._summary_row(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
        )
        metrics = _metrics(_row_values(row))
        previous = None
        if compare:
            previous = await cls._previous_summary(
                account_id,
                window,
                app_id=app_id,
                gateway_id=gateway_id,
                chain=chain,
                network=network,
            )
        return UsageWindow(
            time_range=time_range,
            start_at=window.start_at,
            end_at=window.end_at,
            data_through=window.end_at,
            previous=previous,
            **metrics.model_dump(),
        )

    @classmethod
    async def _previous_summary(
        cls,
        account_id: str,
        window: _Window,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> UsagePreviousWindow:
        previous = _previous_window(window)
        row = await cls._summary_row(
            account_id,
            previous,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
        )
        metrics = _metrics(_row_values(row))
        return UsagePreviousWindow(
            start_at=previous.start_at,
            end_at=previous.end_at,
            **metrics.model_dump(),
        )

    @classmethod
    async def get_series(
        cls,
        account_id: str,
        *,
        time_range: UsageRange,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> UsageSeries:
        window = _usage_window(time_range)
        rows = await cls._series_rows(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
        )
        buckets = cls._buckets(window)
        for row in rows:
            buckets[_db_datetime(row['bucket_start'])] = _row_values(row)
        items = [UsageSeriesPoint(bucket_start=bucket, **_metrics(values).model_dump()) for bucket, values in buckets.items()]
        return UsageSeries(
            time_range=time_range,
            granularity=window.granularity,
            data_through=window.end_at,
            items=items,
        )

    @classmethod
    async def get_methods(
        cls,
        account_id: str,
        *,
        time_range: UsageRange,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
        rank_by: UsageMethodRank,
        limit: int,
    ) -> UsageByMethod:
        window = _usage_window(time_range)
        methods, rows = await cls._method_rows(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
            rank_by=rank_by,
            limit=limit,
        )
        grouped = {method: cls._buckets(window, _METHOD_FIELDS) for method in methods}
        for row in rows:
            method = str(row['method'])
            grouped[method][_db_datetime(row['bucket_start'])] = _row_values(row, _METHOD_FIELDS)
        items = [
            UsageByMethodItem(
                method=method,
                points=[_method_point(bucket, values) for bucket, values in grouped[method].items()],
            )
            for method in methods
        ]
        return UsageByMethod(
            time_range=time_range,
            granularity=window.granularity,
            data_through=window.end_at,
            items=items,
        )

    @classmethod
    async def get_networks(
        cls,
        account_id: str,
        *,
        time_range: UsageRange,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
        limit: int,
    ) -> UsageByNetwork:
        window = _usage_window(time_range)
        rows = await cls._network_rows(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            chain=chain,
            network=network,
        )
        totals: dict[tuple[Chain, Network], int] = {}
        for row in rows:
            dimension = _network_dimension(row)
            total_requests = _row_values(row, ('total_requests',))['total_requests']
            totals[dimension] = totals.get(dimension, 0) + total_requests
        dimensions = sorted(totals, key=lambda item: (-totals[item], item[0].value, item[1].value))[:limit]
        grouped = {dimension: cls._buckets(window, _NETWORK_FIELDS) for dimension in dimensions}
        for row in rows:
            dimension = _network_dimension(row)
            if dimension in grouped:
                grouped[dimension][_db_datetime(row['bucket_start'])] = _row_values(row, _NETWORK_FIELDS)
        items = []
        for item_chain, item_network in dimensions:
            chain_definition = CHAIN_CATALOG[item_chain]
            network_definition = chain_definition.networks[item_network]
            points = [_network_point(bucket, values) for bucket, values in grouped[(item_chain, item_network)].items()]
            items.append(
                UsageByNetworkItem(
                    chain=item_chain,
                    chain_label=chain_definition.label,
                    network=item_network,
                    network_label=network_definition.label,
                    points=points,
                )
            )
        return UsageByNetwork(
            time_range=time_range,
            granularity=window.granularity,
            data_through=window.end_at,
            items=items,
        )

    @classmethod
    async def get_routes(
        cls,
        account_id: str,
        *,
        time_range: UsageRange,
        app_id: str,
        gateway_id: str | None,
        limit: int,
    ) -> UsageByRoute:
        window = _usage_window(time_range)
        coverage_start_at = await cls._coverage_start_at(_ROUTE_USAGE_METRIC)
        route_ids, rows = await cls._route_rows(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            limit=limit,
        )
        grouped = {route_id: cls._buckets(window, _ROUTE_FIELDS) for route_id in route_ids}
        dimensions: dict[str, tuple[str, Chain, Network]] = {}
        totals = {route_id: _empty_values(_ROUTE_FIELDS) for route_id in route_ids}
        for row in rows:
            route_id = str(row['route_id'])
            values = _row_values(row, _ROUTE_FIELDS)
            grouped[route_id][_db_datetime(row['bucket_start'])] = values
            dimensions[route_id] = (str(row['gateway_id']), *_network_dimension(row))
            for field in _ROUTE_FIELDS:
                totals[route_id][field] += values[field]
        items = []
        for route_id in route_ids:
            item_gateway_id, chain, network = dimensions[route_id]
            items.append(
                UsageRouteItem(
                    route_id=route_id,
                    gateway_id=item_gateway_id,
                    chain=chain,
                    network=network,
                    points=[_route_point(bucket, values) for bucket, values in grouped[route_id].items()],
                    **_route_metrics(totals[route_id]).model_dump(),
                )
            )
        return UsageByRoute(
            time_range=time_range,
            granularity=window.granularity,
            start_at=window.start_at,
            end_at=window.end_at,
            data_through=window.end_at,
            coverage_start_at=coverage_start_at,
            coverage_complete=coverage_start_at is not None and coverage_start_at <= window.start_at,
            items=items,
        )

    @classmethod
    async def get_endpoints(
        cls,
        account_id: str,
        *,
        time_range: UsageRange,
        app_id: str | None = None,
        gateway_id: str | None = None,
        route_id: str | None = None,
        limit: int | None = None,
    ) -> UsageByEndpoint:
        window = _usage_window(time_range)
        rows = await cls._endpoint_rows(
            account_id,
            window,
            app_id=app_id,
            gateway_id=gateway_id,
            route_id=route_id,
        )
        coverage_start_at = await cls._coverage_start_at(_ENDPOINT_CLASSIFICATION_METRIC)
        totals: dict[str, dict[str, int]] = {}
        dimensions: dict[str, tuple[Chain, Network]] = {}
        values_by_endpoint: dict[str, dict[datetime, dict[str, int]]] = {}
        for row in rows:
            endpoint_id = str(row['endpoint_id'])
            values = _endpoint_values(row)
            endpoint_totals = totals.setdefault(endpoint_id, _empty_values(_ENDPOINT_FIELDS))
            for field in _ENDPOINT_FIELDS:
                endpoint_totals[field] += values[field]
            dimensions[endpoint_id] = _network_dimension(row)
            values_by_endpoint.setdefault(endpoint_id, {})[_db_datetime(row['bucket_start'])] = values
        ranked_ids = sorted(totals, key=lambda endpoint_id: (-totals[endpoint_id]['total_attempts'], endpoint_id))
        selected_ids = ranked_ids if limit is None else ranked_ids[:limit]
        other_ids = set(ranked_ids[len(selected_ids) :])
        endpoint_rows = await Endpoint.filter(account_id=account_id, id__in=selected_ids).all() if selected_ids else []
        metadata = {row.id: row for row in endpoint_rows}
        bucket_starts = list(cls._buckets(window, _ENDPOINT_FIELDS))
        items: list[UsageEndpointItem] = []
        for endpoint_id in selected_ids:
            chain, network = dimensions[endpoint_id]
            endpoint = metadata.get(endpoint_id)
            items.append(
                UsageEndpointItem(
                    endpoint_id=endpoint_id,
                    name=endpoint.name if endpoint is not None else endpoint_id,
                    chain=chain,
                    network=network,
                    protocol=endpoint.protocol if endpoint is not None else None,
                    historical=endpoint is None or endpoint.deleted_at is not None,
                    **totals[endpoint_id],
                    points=[
                        UsageEndpointPoint(
                            bucket_start=bucket_start,
                            **values_by_endpoint[endpoint_id].get(bucket_start, _empty_values(_ENDPOINT_FIELDS)),
                        )
                        for bucket_start in bucket_starts
                    ],
                )
            )
        other_by_bucket = {bucket_start: _empty_values(_ENDPOINT_FIELDS) for bucket_start in bucket_starts}
        for endpoint_id in other_ids:
            for bucket_start in bucket_starts:
                values = values_by_endpoint[endpoint_id].get(bucket_start, _empty_values(_ENDPOINT_FIELDS))
                for field in _ENDPOINT_FIELDS:
                    other_by_bucket[bucket_start][field] += values[field]
        all_totals = _empty_values(_ENDPOINT_FIELDS)
        other_totals = _empty_values(_ENDPOINT_FIELDS)
        for endpoint_id, values in totals.items():
            for field in _ENDPOINT_FIELDS:
                all_totals[field] += values[field]
                if endpoint_id in other_ids:
                    other_totals[field] += values[field]
        return UsageByEndpoint(
            time_range=time_range,
            granularity=window.granularity,
            start_at=window.start_at,
            end_at=window.end_at,
            data_through=window.end_at,
            classification_coverage_start_at=coverage_start_at,
            classification_coverage_complete=coverage_start_at is not None and coverage_start_at <= window.start_at,
            **all_totals,
            observed_endpoint_count=len(totals),
            items=items,
            other_total_attempts=other_totals['total_attempts'],
            other_first_attempts=other_totals['first_attempts'],
            other_retry_attempts=other_totals['retry_attempts'],
            other_unclassified_attempts=other_totals['unclassified_attempts'],
            other_points=[
                UsageEndpointPoint(bucket_start=bucket_start, **other_by_bucket[bucket_start]) for bucket_start in bucket_starts
            ],
        )

    @staticmethod
    def _buckets(window: _Window, fields: tuple[str, ...] = _FIELDS) -> dict[datetime, dict[str, int]]:
        buckets: dict[datetime, dict[str, int]] = {}
        bucket = window.start_at
        while bucket < window.end_at:
            buckets[bucket] = _empty_values(fields)
            bucket += window.width
        return buckets
