from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from tortoise.functions import Sum
from tortoise.queryset import QuerySet

from app.core.errors import InternalError
from app.model.blockchain import CHAIN_CATALOG, Chain, Network
from app.model.usage import (
    UsageByMethod,
    UsageByMethodItem,
    UsageByNetwork,
    UsageByNetworkItem,
    UsageGranularity,
    UsageMethodPoint,
    UsageMethodRank,
    UsageMetrics,
    UsageNetworkPoint,
    UsageRange,
    UsageSeries,
    UsageSeriesPoint,
    UsageWindow,
)
from app.orm.functions import DateTrunc
from app.orm.usage import GatewayUsageFiveMinute, GatewayUsageHourly, GatewayUsageMethodFiveMinute, GatewayUsageMethodHourly
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
        return UsageWindow(
            time_range=time_range,
            start_at=window.start_at,
            end_at=window.end_at,
            data_through=window.end_at,
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

    @staticmethod
    def _buckets(window: _Window, fields: tuple[str, ...] = _FIELDS) -> dict[datetime, dict[str, int]]:
        buckets: dict[datetime, dict[str, int]] = {}
        bucket = window.start_at
        while bucket < window.end_at:
            buckets[bucket] = _empty_values(fields)
            bucket += window.width
        return buckets
