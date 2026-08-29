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


class Migration(migrations.Migration):
    dependencies = [('models', '0007_provider_networks')]

    initial = False

    operations = [
        ops.CreateModel(
            name='GatewayUsageEndpointFiveMinute',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account_id', fields.CharField(max_length=21)),
                ('app_id', fields.CharField(max_length=21)),
                ('gateway_id', fields.CharField(max_length=21)),
                ('route_id', fields.CharField(max_length=21)),
                ('endpoint_id', fields.CharField(max_length=64)),
                ('chain', fields.CharEnumField(enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(enum_type=Network, max_length=32)),
                ('bucket_start', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('total_attempts', fields.BigIntField(default=0)),
            ],
            options={
                'table': 'gateway_usage_endpoint_five_minute',
                'app': 'models',
                'unique_together': (
                    ('account_id', 'app_id', 'gateway_id', 'route_id', 'endpoint_id', 'chain', 'network', 'bucket_start'),
                ),
                'constraints': [
                    CheckConstraint(check='total_attempts >= 0', name='chk_gateway_usage_endpoint_five_nonnegative'),
                ],
                'indexes': [
                    Index(
                        fields=['account_id', 'gateway_id', 'route_id', 'bucket_start'],
                        name='idx_gateway_usage_endpoint_fine_route_bucket',
                    ),
                ],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='GatewayUsageEndpointHourly',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account_id', fields.CharField(max_length=21)),
                ('app_id', fields.CharField(max_length=21)),
                ('gateway_id', fields.CharField(max_length=21)),
                ('route_id', fields.CharField(max_length=21)),
                ('endpoint_id', fields.CharField(max_length=64)),
                ('chain', fields.CharEnumField(enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(enum_type=Network, max_length=32)),
                ('bucket_hour', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('total_attempts', fields.BigIntField(default=0)),
            ],
            options={
                'table': 'gateway_usage_endpoint_hourly',
                'app': 'models',
                'unique_together': (
                    ('account_id', 'app_id', 'gateway_id', 'route_id', 'endpoint_id', 'chain', 'network', 'bucket_hour'),
                ),
                'constraints': [
                    CheckConstraint(check='total_attempts >= 0', name='chk_gateway_usage_endpoint_hour_nonnegative'),
                ],
                'indexes': [
                    Index(
                        fields=['account_id', 'gateway_id', 'route_id', 'bucket_hour'],
                        name='idx_gateway_usage_endpoint_hour_route_bucket',
                    ),
                ],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
    ]
