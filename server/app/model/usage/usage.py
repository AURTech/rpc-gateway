from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.model.blockchain import Chain, Network, validate_chain_network


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


class UsageGroupedParams(UsageFilterParams):
    limit: int = Field(default=10, ge=1, le=100)


class UsageMethodParams(UsageGroupedParams):
    rank_by: UsageMethodRank = UsageMethodRank.TOTAL_REQUESTS


class UsageNetworkParams(UsageGroupedParams):
    pass


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


class UsageWindow(UsageMetrics):
    time_range: UsageRange
    start_at: datetime
    end_at: datetime
    data_through: datetime


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
