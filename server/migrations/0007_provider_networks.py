from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0006_provider_daily_sync')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Provider',
            name='networks',
            field=fields.JSONField(null=True),
        ),
        ops.RemoveField(model_name='Provider', name='only_networks'),
        ops.RemoveField(model_name='Provider', name='ignore_networks'),
    ]
