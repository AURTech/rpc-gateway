from tortoise import fields
from tortoise.indexes import Index
from tortoise.migrations.constraints import CheckConstraint

from app.model.blockchain import Chain, Network
from app.orm.mixin import GuidMixin, TimestampMixin

_METRIC_CONSTRAINT = """
    total_requests >= 0
    AND successful_requests >= 0
    AND failed_requests >= 0
    AND total_duration_ms >= 0
    AND total_request_bytes >= 0
    AND total_response_bytes >= 0
    AND cache_eligible_requests >= 0
    AND cache_hit_requests >= 0
"""
_ROUTE_METRIC_CONSTRAINT = """
    routed_requests >= 0
    AND successful_requests >= 0
    AND failed_requests >= 0
    AND total_duration_ms >= 0
    AND total_attempts >= 0
    AND multi_attempt_requests >= 0
    AND exhausted_requests >= 0
"""


class GatewayUsageCheckpoint(GuidMixin, TimestampMixin):
    last_stream_id = fields.CharField(max_length=32, default='0-0')

    class Meta:
        table = 'gateway_usage_checkpoint'


class GatewayUsageRollupHour(GuidMixin, TimestampMixin):
    bucket_hour = fields.DatetimeField(unique=True)

    class Meta:
        table = 'gateway_usage_rollup_hour'


class GatewayUsageMetricAvailability(GuidMixin, TimestampMixin):
    metric = fields.CharField(max_length=64, unique=True)
    coverage_start_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'gateway_usage_metric_availability'


class GatewayUsageFiveMinute(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    bucket_start = fields.DatetimeField()
    total_requests = fields.BigIntField(default=0)
    successful_requests = fields.BigIntField(default=0)
    failed_requests = fields.BigIntField(default=0)
    total_duration_ms = fields.BigIntField(default=0)
    total_request_bytes = fields.BigIntField(default=0)
    total_response_bytes = fields.BigIntField(default=0)
    cache_eligible_requests = fields.BigIntField(default=0)
    cache_hit_requests = fields.BigIntField(default=0)

    class Meta:
        table = 'gateway_usage_five_minute'
        unique_together = (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'bucket_start'),)
        constraints = (
            CheckConstraint(check=_METRIC_CONSTRAINT, name='chk_gateway_usage_five_minute_nonnegative'),
            CheckConstraint(
                check='successful_requests + failed_requests = total_requests',
                name='chk_gateway_usage_five_minute_outcomes',
            ),
            CheckConstraint(
                check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests',
                name='chk_gateway_usage_five_minute_cache',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'bucket_start'), name='idx_gateway_usage_five_minute_account_bucket'),
            Index(fields=('account_id', 'app_id', 'bucket_start'), name='idx_gateway_usage_five_minute_account_app_bucket'),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_start'),
                name='idx_gateway_usage_five_minute_account_gateway_bucket',
            ),
            Index(
                fields=('account_id', 'chain', 'network', 'bucket_start'),
                name='idx_gateway_usage_five_minute_account_network_bucket',
            ),
        )


class GatewayUsageMethodFiveMinute(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    method = fields.CharField(max_length=256)
    bucket_start = fields.DatetimeField()
    total_requests = fields.BigIntField(default=0)
    successful_requests = fields.BigIntField(default=0)
    failed_requests = fields.BigIntField(default=0)
    total_duration_ms = fields.BigIntField(default=0)
    total_request_bytes = fields.BigIntField(default=0)
    total_response_bytes = fields.BigIntField(default=0)
    cache_eligible_requests = fields.BigIntField(default=0)
    cache_hit_requests = fields.BigIntField(default=0)

    class Meta:
        table = 'gateway_usage_method_five_minute'
        unique_together = (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'method', 'bucket_start'),)
        constraints = (
            CheckConstraint(check=_METRIC_CONSTRAINT, name='chk_gateway_usage_method_five_minute_nonnegative'),
            CheckConstraint(
                check='successful_requests + failed_requests = total_requests',
                name='chk_gateway_usage_method_five_minute_outcomes',
            ),
            CheckConstraint(
                check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests',
                name='chk_gateway_usage_method_five_minute_cache',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'bucket_start'), name='idx_gateway_usage_method_five_minute_account_bucket'),
            Index(
                fields=('account_id', 'app_id', 'bucket_start'),
                name='idx_gateway_usage_method_five_minute_account_app_bucket',
            ),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_start'),
                name='idx_gateway_usage_method_five_minute_account_gateway_bucket',
            ),
            Index(
                fields=('account_id', 'chain', 'network', 'bucket_start'),
                name='idx_gateway_usage_method_five_minute_account_network_bucket',
            ),
        )


class GatewayUsageEndpointFiveMinute(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    route_id = fields.CharField(max_length=21)
    endpoint_id = fields.CharField(max_length=64)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    bucket_start = fields.DatetimeField()
    total_attempts = fields.BigIntField(default=0)
    first_attempts = fields.BigIntField(null=True)
    retry_attempts = fields.BigIntField(null=True)

    class Meta:
        table = 'gateway_usage_endpoint_five_minute'
        unique_together = (
            ('account_id', 'app_id', 'gateway_id', 'route_id', 'endpoint_id', 'chain', 'network', 'bucket_start'),
        )
        constraints = (
            CheckConstraint(check='total_attempts >= 0', name='chk_gateway_usage_endpoint_five_nonnegative'),
            CheckConstraint(
                check='first_attempts >= 0 AND retry_attempts >= 0',
                name='chk_gateway_usage_endpoint_five_classification',
            ),
            CheckConstraint(
                check='first_attempts + retry_attempts <= total_attempts',
                name='chk_gateway_usage_endpoint_five_attempts',
            ),
        )
        indexes = (
            Index(
                fields=('account_id', 'app_id', 'bucket_start'),
                name='idx_usage_endpoint_fine_account_app_bucket',
            ),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_start'),
                name='idx_usage_endpoint_fine_account_gateway_bucket',
            ),
            Index(
                fields=('account_id', 'gateway_id', 'route_id', 'bucket_start'),
                name='idx_gateway_usage_endpoint_fine_route_bucket',
            ),
        )


class GatewayUsageHourly(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    bucket_hour = fields.DatetimeField()
    total_requests = fields.BigIntField(default=0)
    successful_requests = fields.BigIntField(default=0)
    failed_requests = fields.BigIntField(default=0)
    total_duration_ms = fields.BigIntField(default=0)
    total_request_bytes = fields.BigIntField(default=0)
    total_response_bytes = fields.BigIntField(default=0)
    cache_eligible_requests = fields.BigIntField(default=0)
    cache_hit_requests = fields.BigIntField(default=0)

    class Meta:
        table = 'gateway_usage_hourly'
        unique_together = (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'bucket_hour'),)
        constraints = (
            CheckConstraint(check=_METRIC_CONSTRAINT, name='chk_gateway_usage_hourly_nonnegative'),
            CheckConstraint(
                check='successful_requests + failed_requests = total_requests',
                name='chk_gateway_usage_hourly_outcomes',
            ),
            CheckConstraint(
                check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests',
                name='chk_gateway_usage_hourly_cache',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'bucket_hour'), name='idx_gateway_usage_hourly_account_bucket'),
            Index(fields=('account_id', 'app_id', 'bucket_hour'), name='idx_gateway_usage_hourly_account_app_bucket'),
            Index(fields=('account_id', 'gateway_id', 'bucket_hour'), name='idx_gateway_usage_hourly_account_gateway_bucket'),
            Index(
                fields=('account_id', 'chain', 'network', 'bucket_hour'),
                name='idx_gateway_usage_hourly_account_network_bucket',
            ),
        )


class GatewayUsageMethodHourly(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    method = fields.CharField(max_length=256)
    bucket_hour = fields.DatetimeField()
    total_requests = fields.BigIntField(default=0)
    successful_requests = fields.BigIntField(default=0)
    failed_requests = fields.BigIntField(default=0)
    total_duration_ms = fields.BigIntField(default=0)
    total_request_bytes = fields.BigIntField(default=0)
    total_response_bytes = fields.BigIntField(default=0)
    cache_eligible_requests = fields.BigIntField(default=0)
    cache_hit_requests = fields.BigIntField(default=0)

    class Meta:
        table = 'gateway_usage_method_hourly'
        unique_together = (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'method', 'bucket_hour'),)
        constraints = (
            CheckConstraint(check=_METRIC_CONSTRAINT, name='chk_gateway_usage_method_hourly_nonnegative'),
            CheckConstraint(
                check='successful_requests + failed_requests = total_requests',
                name='chk_gateway_usage_method_hourly_outcomes',
            ),
            CheckConstraint(
                check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests',
                name='chk_gateway_usage_method_hourly_cache',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'bucket_hour'), name='idx_gateway_usage_method_hourly_account_bucket'),
            Index(
                fields=('account_id', 'app_id', 'bucket_hour'),
                name='idx_gateway_usage_method_hourly_account_app_bucket',
            ),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_hour'),
                name='idx_gateway_usage_method_hourly_account_gateway_bucket',
            ),
            Index(
                fields=('account_id', 'chain', 'network', 'bucket_hour'),
                name='idx_gateway_usage_method_hourly_account_network_bucket',
            ),
        )


class GatewayUsageEndpointHourly(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    route_id = fields.CharField(max_length=21)
    endpoint_id = fields.CharField(max_length=64)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    bucket_hour = fields.DatetimeField()
    total_attempts = fields.BigIntField(default=0)
    first_attempts = fields.BigIntField(null=True)
    retry_attempts = fields.BigIntField(null=True)

    class Meta:
        table = 'gateway_usage_endpoint_hourly'
        unique_together = (
            ('account_id', 'app_id', 'gateway_id', 'route_id', 'endpoint_id', 'chain', 'network', 'bucket_hour'),
        )
        constraints = (
            CheckConstraint(check='total_attempts >= 0', name='chk_gateway_usage_endpoint_hour_nonnegative'),
            CheckConstraint(
                check='first_attempts >= 0 AND retry_attempts >= 0',
                name='chk_gateway_usage_endpoint_hour_classification',
            ),
            CheckConstraint(
                check='first_attempts + retry_attempts <= total_attempts',
                name='chk_gateway_usage_endpoint_hour_attempts',
            ),
        )
        indexes = (
            Index(
                fields=('account_id', 'app_id', 'bucket_hour'),
                name='idx_usage_endpoint_hour_account_app_bucket',
            ),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_hour'),
                name='idx_usage_endpoint_hour_account_gateway_bucket',
            ),
            Index(
                fields=('account_id', 'gateway_id', 'route_id', 'bucket_hour'),
                name='idx_gateway_usage_endpoint_hour_route_bucket',
            ),
        )


class GatewayUsageRouteFiveMinute(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    route_id = fields.CharField(max_length=21)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    bucket_start = fields.DatetimeField()
    routed_requests = fields.BigIntField(default=0)
    successful_requests = fields.BigIntField(default=0)
    failed_requests = fields.BigIntField(default=0)
    total_duration_ms = fields.BigIntField(default=0)
    total_attempts = fields.BigIntField(default=0)
    multi_attempt_requests = fields.BigIntField(default=0)
    exhausted_requests = fields.BigIntField(default=0)

    class Meta:
        table = 'gateway_usage_route_five_minute'
        unique_together = (('account_id', 'app_id', 'gateway_id', 'route_id', 'chain', 'network', 'bucket_start'),)
        constraints = (
            CheckConstraint(check=_ROUTE_METRIC_CONSTRAINT, name='chk_gateway_usage_route_five_nonnegative'),
            CheckConstraint(
                check='successful_requests + failed_requests = routed_requests',
                name='chk_gateway_usage_route_five_outcomes',
            ),
            CheckConstraint(
                check='multi_attempt_requests <= routed_requests AND exhausted_requests <= failed_requests',
                name='chk_gateway_usage_route_five_relations',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'app_id', 'bucket_start'), name='idx_usage_route_fine_account_app_bucket'),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_start'),
                name='idx_usage_route_fine_account_gateway_bucket',
            ),
        )


class GatewayUsageRouteHourly(GuidMixin, TimestampMixin):
    account_id = fields.CharField(max_length=21)
    app_id = fields.CharField(max_length=21)
    gateway_id = fields.CharField(max_length=21)
    route_id = fields.CharField(max_length=21)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    bucket_hour = fields.DatetimeField()
    routed_requests = fields.BigIntField(default=0)
    successful_requests = fields.BigIntField(default=0)
    failed_requests = fields.BigIntField(default=0)
    total_duration_ms = fields.BigIntField(default=0)
    total_attempts = fields.BigIntField(default=0)
    multi_attempt_requests = fields.BigIntField(default=0)
    exhausted_requests = fields.BigIntField(default=0)

    class Meta:
        table = 'gateway_usage_route_hourly'
        unique_together = (('account_id', 'app_id', 'gateway_id', 'route_id', 'chain', 'network', 'bucket_hour'),)
        constraints = (
            CheckConstraint(check=_ROUTE_METRIC_CONSTRAINT, name='chk_gateway_usage_route_hour_nonnegative'),
            CheckConstraint(
                check='successful_requests + failed_requests = routed_requests',
                name='chk_gateway_usage_route_hour_outcomes',
            ),
            CheckConstraint(
                check='multi_attempt_requests <= routed_requests AND exhausted_requests <= failed_requests',
                name='chk_gateway_usage_route_hour_relations',
            ),
        )
        indexes = (
            Index(fields=('account_id', 'app_id', 'bucket_hour'), name='idx_usage_route_hour_account_app_bucket'),
            Index(
                fields=('account_id', 'gateway_id', 'bucket_hour'),
                name='idx_usage_route_hour_account_gateway_bucket',
            ),
        )
