from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.model.blockchain import Chain, Network, validate_chain_network
from app.model.endpoint import EndpointProtocol


class UsageRange(StrEnum):
    HOURLY = 'hourly'
    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'


class UsageGranularity(StrEnum):
    FIVE_MINUTE = 'five_minute'
    HOURLY = 'hourly'
    DAILY = 'daily'


class UsageMethodRank(StrEnum):
    TOTAL_REQUESTS = 'total_requests'
    CACHE_ELIGIBLE_REQUESTS = 'cache_eligible_requests'


class _UsageScopeParams(BaseModel):
    time_range: UsageRange = UsageRange.DAILY
    app_id: str | None = Field(default=None, min_length=1, max_length=21)
    chain: Chain | None = None
    network: Network | None = None

    @model_validator(mode='after')
    def validate_network_pair(self) -> Self:
        if self.chain is not None and self.network is not None:
            validate_chain_network(self.chain, self.network)
        return self


class UsageFilterParams(_UsageScopeParams):
    gateway_id: str | None = Field(default=None, min_length=1, max_length=21)


class UsageSummaryParams(UsageFilterParams):
    compare: bool = False


class UsageGroupedParams(UsageFilterParams):
    limit: int = Field(default=10, ge=1, le=100)


class UsageMethodParams(UsageGroupedParams):
    rank_by: UsageMethodRank = UsageMethodRank.TOTAL_REQUESTS


class UsageNetworkParams(UsageGroupedParams):
    pass


class UsageRouteParams(BaseModel):
    time_range: UsageRange = UsageRange.DAILY
    app_id: str = Field(min_length=1, max_length=21)
    gateway_id: str | None = Field(default=None, min_length=1, max_length=21)
    limit: int = Field(default=10, ge=1, le=100)


class UsageEndpointParams(BaseModel):
    time_range: UsageRange = UsageRange.DAILY
    app_id: str | None = Field(default=None, min_length=1, max_length=21)
    gateway_id: str | None = Field(default=None, min_length=1, max_length=21)
    route_id: str | None = Field(default=None, min_length=1, max_length=21)
    limit: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode='after')
    def validate_scope(self) -> Self:
        if self.app_id is None and self.gateway_id is None:
            raise ValueError('app_id or gateway_id is required.')
        if self.route_id is not None and self.gateway_id is None:
            raise ValueError('route_id requires gateway_id.')
        return self


class UsageMetrics(BaseModel):
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    success_rate: float = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0
    total_request_bytes: int = 0
    total_response_bytes: int = 0
    total_traffic_bytes: int = 0
    cache_eligible_requests: int = 0
    cache_hit_requests: int = 0
    cache_hit_rate: float = 0


class UsagePreviousWindow(UsageMetrics):
    start_at: datetime
    end_at: datetime


class UsageWindow(UsageMetrics):
    time_range: UsageRange
    start_at: datetime
    end_at: datetime
    data_through: datetime
    previous: UsagePreviousWindow | None = None


class UsageSeriesPoint(UsageMetrics):
    bucket_start: datetime


class UsageSeries(BaseModel):
    time_range: UsageRange
    granularity: UsageGranularity
    data_through: datetime
    items: list[UsageSeriesPoint]


class UsageMethodPoint(BaseModel):
    bucket_start: datetime
    total_requests: int = 0
    cache_eligible_requests: int = 0
    cache_hit_requests: int = 0
    cache_hit_rate: float = 0


class UsageByMethodItem(BaseModel):
    method: str
    points: list[UsageMethodPoint]


class UsageByMethod(BaseModel):
    time_range: UsageRange
    granularity: UsageGranularity
    data_through: datetime
    items: list[UsageByMethodItem]


class UsageNetworkPoint(BaseModel):
    bucket_start: datetime
    total_requests: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0
    cache_eligible_requests: int = 0
    cache_hit_requests: int = 0
    cache_hit_rate: float = 0


class UsageByNetworkItem(BaseModel):
    chain: Chain
    chain_label: str
    network: Network
    network_label: str
    points: list[UsageNetworkPoint]


class UsageByNetwork(BaseModel):
    time_range: UsageRange
    granularity: UsageGranularity
    data_through: datetime
    items: list[UsageByNetworkItem]


class UsageRouteMetrics(BaseModel):
    routed_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    success_rate: float = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0
    total_attempts: int = 0
    avg_attempts: float = 0
    multi_attempt_requests: int = 0
    multi_attempt_rate: float = 0
    exhausted_requests: int = 0
    exhausted_rate: float = 0


class UsageRoutePoint(UsageRouteMetrics):
    bucket_start: datetime


class UsageRouteItem(UsageRouteMetrics):
    route_id: str
    gateway_id: str
    chain: Chain
    network: Network
    points: list[UsageRoutePoint]


class UsageByRoute(BaseModel):
    time_range: UsageRange
    granularity: UsageGranularity
    start_at: datetime
    end_at: datetime
    data_through: datetime
    coverage_start_at: datetime | None
    coverage_complete: bool
    items: list[UsageRouteItem]


class UsageEndpointPoint(BaseModel):
    bucket_start: datetime
    total_attempts: int = 0
    first_attempts: int = 0
    retry_attempts: int = 0
    unclassified_attempts: int = 0


class UsageEndpointItem(BaseModel):
    endpoint_id: str
    name: str
    chain: Chain
    network: Network
    protocol: EndpointProtocol | None = None
    historical: bool = False
    total_attempts: int = 0
    first_attempts: int = 0
    retry_attempts: int = 0
    unclassified_attempts: int = 0
    points: list[UsageEndpointPoint]


class UsageByEndpoint(BaseModel):
    time_range: UsageRange
    granularity: UsageGranularity
    start_at: datetime
    end_at: datetime
    data_through: datetime
    classification_coverage_start_at: datetime | None
    classification_coverage_complete: bool
    total_attempts: int = 0
    first_attempts: int = 0
    retry_attempts: int = 0
    unclassified_attempts: int = 0
    observed_endpoint_count: int = 0
    items: list[UsageEndpointItem]
    other_total_attempts: int = 0
    other_first_attempts: int = 0
    other_retry_attempts: int = 0
    other_unclassified_attempts: int = 0
    other_points: list[UsageEndpointPoint]
