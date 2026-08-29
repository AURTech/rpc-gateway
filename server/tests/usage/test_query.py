from datetime import UTC, datetime

import pytest
from app.model.blockchain import Chain, Network
from app.model.usage import UsageFilterParams, UsageGranularity, UsageMethodRank, UsageRange
from app.services.usage.query import GatewayUsageQueryManager, _previous_window, _usage_window


def test_usage_ranges_build_expected_windows() -> None:
    now = datetime(2026, 7, 23, 16, 23, tzinfo=UTC)

    hourly = _usage_window(UsageRange.HOURLY, now)
    daily = _usage_window(UsageRange.DAILY, now)
    weekly = _usage_window(UsageRange.WEEKLY, now)
    monthly = _usage_window(UsageRange.MONTHLY, now)

    assert hourly.start_at == datetime(2026, 7, 23, 15, 20, tzinfo=UTC)
    assert hourly.end_at == datetime(2026, 7, 23, 16, 20, tzinfo=UTC)
    assert hourly.granularity is UsageGranularity.FIVE_MINUTE
    assert hourly.end_at - hourly.start_at == hourly.width * 12
    assert daily.granularity is UsageGranularity.HOURLY
    assert daily.end_at == datetime(2026, 7, 23, 16, tzinfo=UTC)
    assert daily.end_at - daily.start_at == daily.width * 24
    assert weekly.granularity is UsageGranularity.DAILY
    assert weekly.end_at == datetime(2026, 7, 23, tzinfo=UTC)
    assert weekly.end_at - weekly.start_at == weekly.width * 7
    assert monthly.end_at == datetime(2026, 7, 23, tzinfo=UTC)
    assert monthly.end_at - monthly.start_at == monthly.width * 30


def test_hourly_usage_window_ends_at_exact_five_minute_boundary() -> None:
    now = datetime(2026, 7, 23, 16, tzinfo=UTC)

    window = _usage_window(UsageRange.HOURLY, now)

    assert window.start_at == datetime(2026, 7, 23, 15, tzinfo=UTC)
    assert window.end_at == now


def test_previous_windows_shift_back_by_one_full_span() -> None:
    now = datetime(2026, 7, 23, 16, 23, tzinfo=UTC)

    for time_range in UsageRange:
        window = _usage_window(time_range, now)
        previous = _previous_window(window)

        assert previous.end_at == window.start_at
        assert window.end_at - window.start_at == previous.end_at - previous.start_at
        assert previous.width == window.width
        assert previous.granularity is window.granularity


def test_usage_filter_params_accept_hourly_range() -> None:
    params = UsageFilterParams.model_validate({'time_range': 'hourly'})

    assert params.time_range is UsageRange.HOURLY


@pytest.mark.anyio
async def test_summary_combines_gateway_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    async def summary_row(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            'total_requests': 4,
            'successful_requests': 3,
            'failed_requests': 1,
            'total_duration_ms': 80,
            'total_request_bytes': 30,
            'total_response_bytes': 130,
            'cache_eligible_requests': 2,
            'cache_hit_requests': 1,
        }

    monkeypatch.setattr(GatewayUsageQueryManager, '_summary_row', summary_row)

    result = await GatewayUsageQueryManager.get_summary(
        'account-1',
        time_range=UsageRange.DAILY,
        app_id=None,
        gateway_id='gateway-1',
        chain=None,
        network=None,
    )

    assert result.total_requests == 4
    assert result.successful_requests == 3
    assert result.success_rate == 0.75
    assert result.avg_duration_ms == 20
    assert result.total_traffic_bytes == 160
    assert result.cache_hit_rate == 0.5


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('time_range', 'expected_count', 'expected_granularity'),
    [
        (UsageRange.HOURLY, 12, UsageGranularity.FIVE_MINUTE),
        (UsageRange.DAILY, 24, UsageGranularity.HOURLY),
        (UsageRange.WEEKLY, 7, UsageGranularity.DAILY),
        (UsageRange.MONTHLY, 30, UsageGranularity.DAILY),
    ],
)
async def test_series_fills_empty_buckets_and_keeps_overview_metrics(
    monkeypatch: pytest.MonkeyPatch,
    time_range: UsageRange,
    expected_count: int,
    expected_granularity: UsageGranularity,
) -> None:
    window = _usage_window(time_range)
    populated_index = 0 if time_range is UsageRange.HOURLY else 1
    populated_bucket = window.start_at + window.width * populated_index

    async def series_rows(
        _account_id: str,
        _window: object,
        *,
        app_id: str | None,
        gateway_id: str | None,
        chain: Chain | None,
        network: Network | None,
    ) -> list[dict[str, object]]:
        return [
            {
                'bucket_start': populated_bucket,
                'total_requests': 5,
                'successful_requests': 4,
                'failed_requests': 1,
                'total_duration_ms': 75,
                'total_request_bytes': 120,
                'total_response_bytes': 880,
                'cache_eligible_requests': 2,
                'cache_hit_requests': 1,
            }
        ]

    monkeypatch.setattr('app.services.usage.query._usage_window', lambda _time_range: window)
    monkeypatch.setattr(GatewayUsageQueryManager, '_series_rows', staticmethod(series_rows))

    result = await GatewayUsageQueryManager.get_series(
        'account-1',
        time_range=time_range,
        app_id=None,
        gateway_id=None,
        chain=None,
        network=None,
    )

    assert result.granularity is expected_granularity
    assert result.data_through == window.end_at
    assert len(result.items) == expected_count
    if populated_index > 0:
        assert result.items[0].total_requests == 0
    populated = result.items[populated_index]
    assert populated.successful_requests == 4
    assert populated.failed_requests == 1
    assert populated.total_request_bytes == 120
    assert populated.total_response_bytes == 880
    assert populated.total_traffic_bytes == 1000


@pytest.mark.anyio
async def test_networks_keep_chain_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _usage_window(UsageRange.DAILY)
    populated_bucket = window.start_at + window.width

    async def network_rows(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        base = {
            'bucket_start': populated_bucket,
            'total_requests': 5,
            'total_duration_ms': 75,
            'cache_eligible_requests': 4,
            'cache_hit_requests': 3,
        }
        return [
            {'chain': 'ethereum', 'network': 'mainnet', **base},
            {'chain': 'polygon', 'network': 'mainnet', **base},
        ]

    monkeypatch.setattr('app.services.usage.query._usage_window', lambda _time_range: window)
    monkeypatch.setattr(GatewayUsageQueryManager, '_network_rows', staticmethod(network_rows))

    result = await GatewayUsageQueryManager.get_networks(
        'account-1',
        time_range=UsageRange.DAILY,
        app_id=None,
        gateway_id=None,
        chain=None,
        network=None,
        limit=10,
    )

    assert [(item.chain, item.network) for item in result.items] == [
        (Chain.ETHEREUM, Network.MAINNET),
        (Chain.POLYGON, Network.MAINNET),
    ]
    assert [item.chain_label for item in result.items] == ['Ethereum', 'Polygon']
    assert result.data_through == window.end_at
    assert all(len(item.points) == 24 for item in result.items)
    assert [item.points[1].total_requests for item in result.items] == [5, 5]
    assert [item.points[1].avg_duration_ms for item in result.items] == [15, 15]
    assert [item.points[1].cache_hit_rate for item in result.items] == [0.75, 0.75]


@pytest.mark.anyio
async def test_methods_return_narrow_request_and_cache_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _usage_window(UsageRange.DAILY)
    populated_bucket = window.start_at + window.width

    async def method_rows(*_args: object, **_kwargs: object) -> tuple[list[str], list[dict[str, object]]]:
        return ['eth_call'], [
            {
                'method': 'eth_call',
                'bucket_start': populated_bucket,
                'total_requests': 5,
                'cache_eligible_requests': 4,
                'cache_hit_requests': 3,
            }
        ]

    monkeypatch.setattr('app.services.usage.query._usage_window', lambda _time_range: window)
    monkeypatch.setattr(GatewayUsageQueryManager, '_method_rows', staticmethod(method_rows))

    result = await GatewayUsageQueryManager.get_methods(
        'account-1',
        time_range=UsageRange.DAILY,
        app_id=None,
        gateway_id=None,
        chain=None,
        network=None,
        rank_by=UsageMethodRank.CACHE_ELIGIBLE_REQUESTS,
        limit=10,
    )

    assert result.data_through == window.end_at
    assert len(result.items[0].points) == 24
    assert result.items[0].points[0].total_requests == 0
    populated = result.items[0].points[1]
    assert populated.total_requests == 5
    assert populated.cache_eligible_requests == 4
    assert populated.cache_hit_requests == 3
    assert populated.cache_hit_rate == 0.75


@pytest.mark.anyio
async def test_endpoints_return_route_attempt_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _usage_window(UsageRange.DAILY)

    async def endpoint_rows(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        return [
            {
                'endpoint_id': 'endpoint-1',
                'chain': 'ethereum',
                'network': 'mainnet',
                'bucket_start': window.start_at,
                'metric_total_attempts': 8,
                'metric_first_attempts': 5,
                'metric_retry_attempts': 2,
            },
            {
                'endpoint_id': 'endpoint-2',
                'chain': 'ethereum',
                'network': 'mainnet',
                'bucket_start': window.start_at,
                'metric_total_attempts': 3,
                'metric_first_attempts': 2,
                'metric_retry_attempts': 1,
            },
        ]

    class EndpointQuery:
        async def all(self) -> list[object]:
            return []

    async def coverage_start_at(_metric: str) -> None:
        return None

    monkeypatch.setattr('app.services.usage.query._usage_window', lambda _time_range: window)
    monkeypatch.setattr(GatewayUsageQueryManager, '_endpoint_rows', staticmethod(endpoint_rows))
    monkeypatch.setattr(GatewayUsageQueryManager, '_coverage_start_at', staticmethod(coverage_start_at))
    monkeypatch.setattr('app.services.usage.query.Endpoint.filter', lambda **_kwargs: EndpointQuery())

    result = await GatewayUsageQueryManager.get_endpoints(
        'account-1',
        time_range=UsageRange.DAILY,
        gateway_id='gateway-1',
        route_id='route-1',
    )

    assert result.total_attempts == 11
    assert result.first_attempts == 7
    assert result.retry_attempts == 3
    assert result.unclassified_attempts == 1
    assert result.observed_endpoint_count == 2
    assert [
        (item.endpoint_id, item.total_attempts, item.first_attempts, item.retry_attempts, item.unclassified_attempts)
        for item in result.items
    ] == [
        ('endpoint-1', 8, 5, 2, 1),
        ('endpoint-2', 3, 2, 1, 0),
    ]
    assert result.start_at == window.start_at
    assert result.data_through == window.end_at
    assert result.classification_coverage_start_at is None
    assert not result.classification_coverage_complete


@pytest.mark.anyio
async def test_routes_return_ranked_summaries_and_series(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _usage_window(UsageRange.DAILY)
    populated_bucket = window.start_at + window.width

    async def route_rows(*_args: object, **_kwargs: object) -> tuple[list[str], list[dict[str, object]]]:
        return ['route-2', 'route-1'], [
            {
                'route_id': 'route-2',
                'gateway_id': 'gateway-1',
                'chain': 'ethereum',
                'network': 'mainnet',
                'bucket_start': populated_bucket,
                'metric_routed_requests': 4,
                'metric_successful_requests': 3,
                'metric_failed_requests': 1,
                'metric_total_duration_ms': 80,
                'metric_total_attempts': 7,
                'metric_multi_attempt_requests': 2,
                'metric_exhausted_requests': 1,
            },
            {
                'route_id': 'route-1',
                'gateway_id': 'gateway-1',
                'chain': 'ethereum',
                'network': 'mainnet',
                'bucket_start': populated_bucket,
                'metric_routed_requests': 2,
                'metric_successful_requests': 2,
                'metric_failed_requests': 0,
                'metric_total_duration_ms': 20,
                'metric_total_attempts': 2,
                'metric_multi_attempt_requests': 0,
                'metric_exhausted_requests': 0,
            },
        ]

    async def coverage_start_at(_metric: str) -> datetime:
        return window.start_at + window.width

    monkeypatch.setattr('app.services.usage.query._usage_window', lambda _time_range: window)
    monkeypatch.setattr(GatewayUsageQueryManager, '_route_rows', staticmethod(route_rows))
    monkeypatch.setattr(GatewayUsageQueryManager, '_coverage_start_at', staticmethod(coverage_start_at))

    result = await GatewayUsageQueryManager.get_routes(
        'account-1',
        time_range=UsageRange.DAILY,
        app_id='app-1',
        gateway_id='gateway-1',
        limit=10,
    )

    assert [item.route_id for item in result.items] == ['route-2', 'route-1']
    assert result.items[0].routed_requests == 4
    assert result.items[0].success_rate == 0.75
    assert result.items[0].avg_duration_ms == 20
    assert result.items[0].avg_attempts == 1.75
    assert result.items[0].multi_attempt_rate == 0.5
    assert result.items[0].exhausted_rate == 1
    assert result.coverage_start_at == window.start_at + window.width
    assert not result.coverage_complete
    assert len(result.items[0].points) == 24
    assert result.items[0].points[1].total_attempts == 7
