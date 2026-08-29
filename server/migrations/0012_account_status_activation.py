from app.model.account.status import AccountStatus
from tortoise import fields, migrations
from tortoise.migrations import operations as ops

# Activation is tracked by `first_login_at`, so the removed `unactivated` status collapses into `active`.
# Deployment order matters: apply this migration BEFORE starting the new API/worker/scheduler, because
# `AccountStatus('unactivated')` now raises on read. Roll back in the reverse order: stop the new code
# first, then run the reverse SQL.
FORWARD_SQL = """
UPDATE account
SET status = 'active'
WHERE status = 'unactivated';
"""

REVERSE_SQL = """
UPDATE account
SET status = 'unactivated'
WHERE status = 'active' AND first_login_at IS NULL;
"""

STATUS_DESCRIPTION = 'ACTIVE: active\nDISABLED: disabled\nARCHIVED: archived'


class Migration(migrations.Migration):
    dependencies = [('models', '0011_provider_cleanup')]

    initial = False

    operations = [
        ops.RunSQL(FORWARD_SQL, REVERSE_SQL),
        ops.AlterField(
            model_name='Account',
            name='status',
            field=fields.CharEnumField(
                default=AccountStatus.ACTIVE,
                description=STATUS_DESCRIPTION,
                enum_type=AccountStatus,
                max_length=32,
            ),
        ),
    ]


# pyright: reportArgumentType=false, reportAssignmentType=false
# Reason: Tortoise migration fields use generated schema-state types that are narrower than runtime values.
