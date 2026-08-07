# ruff: noqa: E501

import app.orm.mixin
from app.orm.mixin import NANOIDField
from orjson import loads
from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.fields.data import JSON_DUMPS
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0003_auto_20260803_0711')]

    initial = False

    operations = [
        ops.CreateModel(
            name='PersonalAccessToken',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                (
                    'account',
                    fields.ForeignKeyField(
                        'models.Account',
                        source_field='account_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='personal_access_tokens',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('name', fields.CharField(max_length=64)),
                ('token_digest', fields.CharField(unique=True, max_length=64)),
                ('token_prefix', fields.CharField(max_length=20)),
                ('scopes', fields.JSONField(encoder=JSON_DUMPS, decoder=loads)),
                ('expires_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('last_used_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('revoked_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={
                'table': 'personal_access_token',
                'app': 'models',
                'indexes': [
                    Index(fields=['account_id', 'deleted_at', 'created_at'], name='idx_personal_access_token_account_created'),
                    Index(
                        fields=['account_id', 'deleted_at', 'revoked_at', 'expires_at'], name='idx_personal_access_token_state'
                    ),
                ],
                'pk_attr': 'id',
            },
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.AddField(
            model_name='AppAuditEvent',
            name='actor_token_id',
            field=fields.CharField(null=True, max_length=21),
        ),
        ops.AddField(
            model_name='EndpointAuditEvent',
            name='actor_token_id',
            field=fields.CharField(null=True, max_length=21),
        ),
        ops.AddField(
            model_name='HttpApiRateLimitAuditEvent',
            name='actor_token_id',
            field=fields.CharField(null=True, max_length=21),
        ),
        ops.AddField(
            model_name='JsonRpcRateLimitAuditEvent',
            name='actor_token_id',
            field=fields.CharField(null=True, max_length=21),
        ),
    ]
