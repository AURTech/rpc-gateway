from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0012_account_status_activation')]

    initial = False

    operations = [
        ops.RemoveField(model_name='Endpoint', name='trust_level'),
        ops.RemoveField(model_name='HttpApiRoute', name='minimum_trust'),
        ops.RemoveField(model_name='JsonRpcRoute', name='minimum_trust'),
    ]
