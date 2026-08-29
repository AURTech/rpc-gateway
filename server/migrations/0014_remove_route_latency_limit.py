from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0013_remove_endpoint_trust')]

    initial = False

    operations = [
        ops.RemoveField(model_name='HttpApiRoute', name='max_latency_ms'),
        ops.RemoveField(model_name='JsonRpcRoute', name='max_latency_ms'),
    ]
