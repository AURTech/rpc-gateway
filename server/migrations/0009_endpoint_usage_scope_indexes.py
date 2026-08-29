from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [
        ('models', '0008_endpoint_usage'),
        ('models', '0008_system_cache_transport'),
    ]

    initial = False

    operations = [
        ops.AddIndex(
            model_name='GatewayUsageEndpointFiveMinute',
            index=Index(
                fields=['account_id', 'app_id', 'bucket_start'],
                name='idx_usage_endpoint_fine_account_app_bucket',
            ),
        ),
        ops.AddIndex(
            model_name='GatewayUsageEndpointFiveMinute',
            index=Index(
                fields=['account_id', 'gateway_id', 'bucket_start'],
                name='idx_usage_endpoint_fine_account_gateway_bucket',
            ),
        ),
        ops.AddIndex(
            model_name='GatewayUsageEndpointHourly',
            index=Index(
                fields=['account_id', 'app_id', 'bucket_hour'],
                name='idx_usage_endpoint_hour_account_app_bucket',
            ),
        ),
        ops.AddIndex(
            model_name='GatewayUsageEndpointHourly',
            index=Index(
                fields=['account_id', 'gateway_id', 'bucket_hour'],
                name='idx_usage_endpoint_hour_account_gateway_bucket',
            ),
        ),
    ]
