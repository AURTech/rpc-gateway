# ruff: noqa: E501
# pyright: reportArgumentType=false, reportAssignmentType=false
# Reason: Tortoise migration fields use generated schema-state types that are narrower than runtime values.

import app.orm.mixin
from app.model.blockchain import Chain, Network
from app.orm.mixin import NANOIDField
from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops
from tortoise.migrations.constraints import CheckConstraint

_ROUTE_METRIC_CONSTRAINT = """
    routed_requests >= 0
    AND successful_requests >= 0
    AND failed_requests >= 0
    AND total_duration_ms >= 0
    AND total_attempts >= 0
    AND multi_attempt_requests >= 0
    AND exhausted_requests >= 0
"""


class Migration(migrations.Migration):
    dependencies = [('models', '0014_remove_route_latency_limit')]

    initial = False

    operations = [
        ops.AddField(
            model_name='GatewayUsageEndpointFiveMinute',
            name='first_attempts',
            field=fields.BigIntField(null=True),
        ),
        ops.AddField(
            model_name='GatewayUsageEndpointFiveMinute',
            name='retry_attempts',
            field=fields.BigIntField(null=True),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageEndpointFiveMinute',
            constraint=CheckConstraint(
                check='first_attempts >= 0 AND retry_attempts >= 0',
                name='chk_gateway_usage_endpoint_five_classification',
            ),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageEndpointFiveMinute',
            constraint=CheckConstraint(
                check='first_attempts + retry_attempts <= total_attempts',
                name='chk_gateway_usage_endpoint_five_attempts',
            ),
        ),
        ops.AddField(
            model_name='GatewayUsageEndpointHourly',
            name='first_attempts',
            field=fields.BigIntField(null=True),
        ),
        ops.AddField(
            model_name='GatewayUsageEndpointHourly',
            name='retry_attempts',
            field=fields.BigIntField(null=True),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageEndpointHourly',
            constraint=CheckConstraint(
                check='first_attempts >= 0 AND retry_attempts >= 0',
                name='chk_gateway_usage_endpoint_hour_classification',
            ),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageEndpointHourly',
            constraint=CheckConstraint(
                check='first_attempts + retry_attempts <= total_attempts',
                name='chk_gateway_usage_endpoint_hour_attempts',
            ),
        ),
        ops.CreateModel(
            name='GatewayUsageMetricAvailability',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('metric', fields.CharField(max_length=64, unique=True)),
                ('coverage_start_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'gateway_usage_metric_availability', 'app': 'models', 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.RunSQL(
            """
            INSERT INTO gateway_usage_metric_availability (
                id, metric, created_at, modified_at
            ) VALUES
                ('usage-route-coverage', 'route_usage', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('usage-endpoint-class', 'endpoint_attempt_classification', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            """
            DELETE FROM gateway_usage_metric_availability
            WHERE metric IN ('route_usage', 'endpoint_attempt_classification')
            """,
        ),
        ops.CreateModel(
            name='GatewayUsageRouteFiveMinute',
            fields=[  # ty: ignore[invalid-argument-type]
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account_id', fields.CharField(max_length=21)),
                ('app_id', fields.CharField(max_length=21)),
                ('gateway_id', fields.CharField(max_length=21)),
                ('route_id', fields.CharField(max_length=21)),
                ('chain', fields.CharEnumField(enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(enum_type=Network, max_length=32)),
                ('bucket_start', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('routed_requests', fields.BigIntField(default=0)),
                ('successful_requests', fields.BigIntField(default=0)),
                ('failed_requests', fields.BigIntField(default=0)),
                ('total_duration_ms', fields.BigIntField(default=0)),
                ('total_attempts', fields.BigIntField(default=0)),
                ('multi_attempt_requests', fields.BigIntField(default=0)),
                ('exhausted_requests', fields.BigIntField(default=0)),
            ],
            options={
                'table': 'gateway_usage_route_five_minute',
                'app': 'models',
                'unique_together': (('account_id', 'app_id', 'gateway_id', 'route_id', 'chain', 'network', 'bucket_start'),),
                'indexes': [
                    Index(
                        fields=['account_id', 'app_id', 'bucket_start'],
                        name='idx_usage_route_fine_account_app_bucket',
                    ),
                    Index(
                        fields=['account_id', 'gateway_id', 'bucket_start'],
                        name='idx_usage_route_fine_account_gateway_bucket',
                    ),
                ],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='GatewayUsageRouteHourly',
            fields=[  # ty: ignore[invalid-argument-type]
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account_id', fields.CharField(max_length=21)),
                ('app_id', fields.CharField(max_length=21)),
                ('gateway_id', fields.CharField(max_length=21)),
                ('route_id', fields.CharField(max_length=21)),
                ('chain', fields.CharEnumField(enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(enum_type=Network, max_length=32)),
                ('bucket_hour', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('routed_requests', fields.BigIntField(default=0)),
                ('successful_requests', fields.BigIntField(default=0)),
                ('failed_requests', fields.BigIntField(default=0)),
                ('total_duration_ms', fields.BigIntField(default=0)),
                ('total_attempts', fields.BigIntField(default=0)),
                ('multi_attempt_requests', fields.BigIntField(default=0)),
                ('exhausted_requests', fields.BigIntField(default=0)),
            ],
            options={
                'table': 'gateway_usage_route_hourly',
                'app': 'models',
                'unique_together': (('account_id', 'app_id', 'gateway_id', 'route_id', 'chain', 'network', 'bucket_hour'),),
                'indexes': [
                    Index(
                        fields=['account_id', 'app_id', 'bucket_hour'],
                        name='idx_usage_route_hour_account_app_bucket',
                    ),
                    Index(
                        fields=['account_id', 'gateway_id', 'bucket_hour'],
                        name='idx_usage_route_hour_account_gateway_bucket',
                    ),
                ],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.AddConstraint(
            model_name='GatewayUsageRouteFiveMinute',
            constraint=CheckConstraint(check=_ROUTE_METRIC_CONSTRAINT, name='chk_gateway_usage_route_five_nonnegative'),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageRouteFiveMinute',
            constraint=CheckConstraint(
                check='successful_requests + failed_requests = routed_requests',
                name='chk_gateway_usage_route_five_outcomes',
            ),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageRouteFiveMinute',
            constraint=CheckConstraint(
                check='multi_attempt_requests <= routed_requests AND exhausted_requests <= failed_requests',
                name='chk_gateway_usage_route_five_relations',
            ),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageRouteHourly',
            constraint=CheckConstraint(check=_ROUTE_METRIC_CONSTRAINT, name='chk_gateway_usage_route_hour_nonnegative'),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageRouteHourly',
            constraint=CheckConstraint(
                check='successful_requests + failed_requests = routed_requests',
                name='chk_gateway_usage_route_hour_outcomes',
            ),
        ),
        ops.AddConstraint(
            model_name='GatewayUsageRouteHourly',
            constraint=CheckConstraint(
                check='multi_attempt_requests <= routed_requests AND exhausted_requests <= failed_requests',
                name='chk_gateway_usage_route_hour_relations',
            ),
        ),
    ]
