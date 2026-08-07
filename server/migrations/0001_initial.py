# ruff: noqa: E501, I001
# pyright: reportArgumentType=false, reportAssignmentType=false
# fmt: off
# Reason: Tortoise migration values and layout are generated for stable schema-state serialization.

import app.orm.mixin
from orjson import loads
from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.fields.data import JSON_DUMPS
from tortoise.indexes import Index
from tortoise.migrations import operations as ops
from tortoise.migrations.constraints import CheckConstraint, UniqueConstraint
from tortoise.migrations.schema_editor.base import BaseSchemaEditor
from tortoise.migrations.schema_generator.state import State

from app.model.account.role import AccountRole
from app.model.account.status import AccountStatus
from app.model.admission.runtime import AdmissionMode
from app.model.application.application import AppAuditAction
from app.model.auth.auth import AuthProvider
from app.model.blockchain import Chain, Network
from app.model.endpoint.endpoint import EndpointAuditAction, EndpointAuthType, EndpointProtocol, EndpointTrustLevel
from app.model.http_api_route.route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.model.jsonrpc_route.route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType
from app.model.provider_state import ProviderSyncStatus, ProviderVendor
from app.orm.mixin import NANOIDField


_USAGE_STATE_OPERATIONS = [
    ops.CreateModel(
        name='GatewayUsageCheckpoint',
        fields=[
            ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
            ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ('last_stream_id', fields.CharField(default='0-0', max_length=32)),
        ],
        options={'table': 'gateway_usage_checkpoint', 'app': 'models', 'pk_attr': 'id'},
        bases=['GuidMixin', 'TimestampMixin'],
    ),
    ops.CreateModel(
        name='GatewayUsageHourly',
        fields=[
            ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
            ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ('account_id', fields.CharField(max_length=21)),
            ('app_id', fields.CharField(max_length=21)),
            ('gateway_id', fields.CharField(max_length=21)),
            ('chain', fields.CharEnumField(enum_type=Chain, max_length=32)),
            ('network', fields.CharEnumField(enum_type=Network, max_length=32)),
            ('bucket_hour', fields.DatetimeField(auto_now=False, auto_now_add=False)),
            ('total_requests', fields.BigIntField(default=0)),
            ('successful_requests', fields.BigIntField(default=0)),
            ('failed_requests', fields.BigIntField(default=0)),
            ('total_duration_ms', fields.BigIntField(default=0)),
            ('total_request_bytes', fields.BigIntField(default=0)),
            ('total_response_bytes', fields.BigIntField(default=0)),
            ('cache_eligible_requests', fields.BigIntField(default=0)),
            ('cache_hit_requests', fields.BigIntField(default=0)),
        ],
        options={
            'table': 'gateway_usage_hourly',
            'app': 'models',
            'unique_together': (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'bucket_hour'),),
            'constraints': [
                CheckConstraint(
                    check='\n    total_requests >= 0\n    AND successful_requests >= 0\n    AND failed_requests >= 0\n    AND total_duration_ms >= 0\n    AND total_request_bytes >= 0\n    AND total_response_bytes >= 0\n    AND cache_eligible_requests >= 0\n    AND cache_hit_requests >= 0\n',
                    name='chk_gateway_usage_hourly_nonnegative',
                ),
                CheckConstraint(
                    check='successful_requests + failed_requests = total_requests',
                    name='chk_gateway_usage_hourly_outcomes',
                ),
                CheckConstraint(
                    check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests',
                    name='chk_gateway_usage_hourly_cache',
                ),
            ],
            'indexes': [
                Index(fields=['account_id', 'bucket_hour'], name='idx_gateway_usage_hourly_account_bucket'),
                Index(fields=['account_id', 'app_id', 'bucket_hour'], name='idx_gateway_usage_hourly_account_app_bucket'),
                Index(
                    fields=['account_id', 'gateway_id', 'bucket_hour'],
                    name='idx_gateway_usage_hourly_account_gateway_bucket',
                ),
                Index(
                    fields=['account_id', 'chain', 'network', 'bucket_hour'],
                    name='idx_gateway_usage_hourly_account_network_bucket',
                ),
            ],
            'pk_attr': 'id',
        },
        bases=['GuidMixin', 'TimestampMixin'],
    ),
    ops.CreateModel(
        name='GatewayUsageMethodHourly',
        fields=[
            ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
            ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ('account_id', fields.CharField(max_length=21)),
            ('app_id', fields.CharField(max_length=21)),
            ('gateway_id', fields.CharField(max_length=21)),
            ('chain', fields.CharEnumField(enum_type=Chain, max_length=32)),
            ('network', fields.CharEnumField(enum_type=Network, max_length=32)),
            ('method', fields.CharField(max_length=256)),
            ('bucket_hour', fields.DatetimeField(auto_now=False, auto_now_add=False)),
            ('total_requests', fields.BigIntField(default=0)),
            ('successful_requests', fields.BigIntField(default=0)),
            ('failed_requests', fields.BigIntField(default=0)),
            ('total_duration_ms', fields.BigIntField(default=0)),
            ('total_request_bytes', fields.BigIntField(default=0)),
            ('total_response_bytes', fields.BigIntField(default=0)),
            ('cache_eligible_requests', fields.BigIntField(default=0)),
            ('cache_hit_requests', fields.BigIntField(default=0)),
        ],
        options={
            'table': 'gateway_usage_method_hourly',
            'app': 'models',
            'unique_together': (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'method', 'bucket_hour'),),
            'constraints': [
                CheckConstraint(
                    check='\n    total_requests >= 0\n    AND successful_requests >= 0\n    AND failed_requests >= 0\n    AND total_duration_ms >= 0\n    AND total_request_bytes >= 0\n    AND total_response_bytes >= 0\n    AND cache_eligible_requests >= 0\n    AND cache_hit_requests >= 0\n',
                    name='chk_gateway_usage_method_hourly_nonnegative',
                ),
                CheckConstraint(
                    check='successful_requests + failed_requests = total_requests',
                    name='chk_gateway_usage_method_hourly_outcomes',
                ),
                CheckConstraint(
                    check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests',
                    name='chk_gateway_usage_method_hourly_cache',
                ),
            ],
            'indexes': [
                Index(fields=['account_id', 'bucket_hour'], name='idx_gateway_usage_method_hourly_account_bucket'),
                Index(
                    fields=['account_id', 'app_id', 'bucket_hour'],
                    name='idx_gateway_usage_method_hourly_account_app_bucket',
                ),
                Index(
                    fields=['account_id', 'gateway_id', 'bucket_hour'],
                    name='idx_gateway_usage_method_hourly_account_gateway_bucket',
                ),
                Index(
                    fields=['account_id', 'chain', 'network', 'bucket_hour'],
                    name='idx_gateway_usage_method_hourly_account_network_bucket',
                ),
            ],
            'pk_attr': 'id',
        },
        bases=['GuidMixin', 'TimestampMixin'],
    ),
]


class PartitionedUsageState(ops.TortoiseOperation):
    """Track the partitioned usage tables without creating ordinary ORM tables."""

    reduces_to_sql = False

    def state_forward(self, app_label: str, state: State) -> None:
        for operation in _USAGE_STATE_OPERATIONS:
            operation.state_forward(app_label, state)

    async def database_forward(
        self,
        app_label: str,
        old_state: State,
        new_state: State,
        state_editor: BaseSchemaEditor | None = None,
    ) -> None:
        return None

    async def database_backward(
        self,
        app_label: str,
        old_state: State,
        new_state: State,
        state_editor: BaseSchemaEditor | None = None,
    ) -> None:
        return None


FORWARD_SQL = [
    """
    ALTER TABLE endpoint
    ADD CONSTRAINT chk_endpoint_auth_columns CHECK (
        (
            auth_type = 'none'
            AND auth_header_name IS NULL
            AND auth_query_param IS NULL
            AND encrypted_auth_secret IS NULL
        )
        OR (
            auth_type IN ('bearer', 'path_api_key')
            AND auth_header_name IS NULL
            AND auth_query_param IS NULL
            AND encrypted_auth_secret IS NOT NULL
        )
        OR (
            auth_type = 'header_api_key'
            AND NULLIF(BTRIM(auth_header_name), '') IS NOT NULL
            AND auth_query_param IS NULL
            AND encrypted_auth_secret IS NOT NULL
        )
        OR (
            auth_type = 'query_api_key'
            AND auth_header_name IS NULL
            AND NULLIF(BTRIM(auth_query_param), '') IS NOT NULL
            AND encrypted_auth_secret IS NOT NULL
        )
    )
    """,
    """
    ALTER TABLE system_jsonrpc_cache_payload
    ADD CONSTRAINT chk_system_jsonrpc_cache_payload_size CHECK (payload_size = octet_length(payload))
    """,
    """
    CREATE UNIQUE INDEX uq_provider_active_account_name
    ON provider (account_id, name)
    WHERE deleted_at IS NULL
    """,
    """
    CREATE TABLE gateway_usage_checkpoint (
        id CHAR(21) PRIMARY KEY CHECK (id = 'usage-v3-checkpoint'),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ,
        last_stream_id VARCHAR(32) NOT NULL DEFAULT '0-0',
        CHECK (deleted_at IS NULL)
    )
    """,
    "INSERT INTO gateway_usage_checkpoint (id, last_stream_id) VALUES ('usage-v3-checkpoint', '0-0')",
    """
    CREATE TABLE gateway_usage_hourly (
        id CHAR(21) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ,
        account_id VARCHAR(21) NOT NULL,
        app_id VARCHAR(21) NOT NULL,
        gateway_id VARCHAR(21) NOT NULL,
        chain VARCHAR(32) NOT NULL,
        network VARCHAR(32) NOT NULL,
        bucket_hour TIMESTAMPTZ NOT NULL,
        total_requests BIGINT NOT NULL DEFAULT 0,
        successful_requests BIGINT NOT NULL DEFAULT 0,
        failed_requests BIGINT NOT NULL DEFAULT 0,
        total_duration_ms BIGINT NOT NULL DEFAULT 0,
        total_request_bytes BIGINT NOT NULL DEFAULT 0,
        total_response_bytes BIGINT NOT NULL DEFAULT 0,
        cache_eligible_requests BIGINT NOT NULL DEFAULT 0,
        cache_hit_requests BIGINT NOT NULL DEFAULT 0,
        CONSTRAINT uq_gateway_usage_hourly_scope
            UNIQUE (account_id, app_id, gateway_id, chain, network, bucket_hour),
        CONSTRAINT chk_gateway_usage_hourly_nonnegative CHECK (
            total_requests >= 0
            AND successful_requests >= 0
            AND failed_requests >= 0
            AND total_duration_ms >= 0
            AND total_request_bytes >= 0
            AND total_response_bytes >= 0
            AND cache_eligible_requests >= 0
            AND cache_hit_requests >= 0
        ),
        CONSTRAINT chk_gateway_usage_hourly_outcomes CHECK (
            successful_requests + failed_requests = total_requests
        ),
        CONSTRAINT chk_gateway_usage_hourly_cache CHECK (
            cache_hit_requests <= cache_eligible_requests
            AND cache_eligible_requests <= total_requests
        )
    ) PARTITION BY RANGE (bucket_hour)
    """,
    """
    CREATE TABLE gateway_usage_method_hourly (
        id CHAR(21) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ,
        account_id VARCHAR(21) NOT NULL,
        app_id VARCHAR(21) NOT NULL,
        gateway_id VARCHAR(21) NOT NULL,
        chain VARCHAR(32) NOT NULL,
        network VARCHAR(32) NOT NULL,
        method VARCHAR(256) NOT NULL,
        bucket_hour TIMESTAMPTZ NOT NULL,
        total_requests BIGINT NOT NULL DEFAULT 0,
        successful_requests BIGINT NOT NULL DEFAULT 0,
        failed_requests BIGINT NOT NULL DEFAULT 0,
        total_duration_ms BIGINT NOT NULL DEFAULT 0,
        total_request_bytes BIGINT NOT NULL DEFAULT 0,
        total_response_bytes BIGINT NOT NULL DEFAULT 0,
        cache_eligible_requests BIGINT NOT NULL DEFAULT 0,
        cache_hit_requests BIGINT NOT NULL DEFAULT 0,
        CONSTRAINT uq_gateway_usage_method_hourly_scope
            UNIQUE (account_id, app_id, gateway_id, chain, network, method, bucket_hour),
        CONSTRAINT chk_gateway_usage_method_hourly_nonnegative CHECK (
            total_requests >= 0
            AND successful_requests >= 0
            AND failed_requests >= 0
            AND total_duration_ms >= 0
            AND total_request_bytes >= 0
            AND total_response_bytes >= 0
            AND cache_eligible_requests >= 0
            AND cache_hit_requests >= 0
        ),
        CONSTRAINT chk_gateway_usage_method_hourly_outcomes CHECK (
            successful_requests + failed_requests = total_requests
        ),
        CONSTRAINT chk_gateway_usage_method_hourly_cache CHECK (
            cache_hit_requests <= cache_eligible_requests
            AND cache_eligible_requests <= total_requests
        )
    ) PARTITION BY RANGE (bucket_hour)
    """,
    'CREATE INDEX idx_gateway_usage_hourly_account_bucket ON gateway_usage_hourly (account_id, bucket_hour)',
    'CREATE INDEX idx_gateway_usage_hourly_account_app_bucket ON gateway_usage_hourly (account_id, app_id, bucket_hour)',
    """
    CREATE INDEX idx_gateway_usage_hourly_account_gateway_bucket
    ON gateway_usage_hourly (account_id, gateway_id, bucket_hour)
    """,
    """
    CREATE INDEX idx_gateway_usage_hourly_account_network_bucket
    ON gateway_usage_hourly (account_id, chain, network, bucket_hour)
    """,
    """
    CREATE INDEX idx_gateway_usage_method_hourly_account_bucket
    ON gateway_usage_method_hourly (account_id, bucket_hour)
    """,
    """
    CREATE INDEX idx_gateway_usage_method_hourly_account_app_bucket
    ON gateway_usage_method_hourly (account_id, app_id, bucket_hour)
    """,
    """
    CREATE INDEX idx_gateway_usage_method_hourly_account_gateway_bucket
    ON gateway_usage_method_hourly (account_id, gateway_id, bucket_hour)
    """,
    """
    CREATE INDEX idx_gateway_usage_method_hourly_account_network_bucket
    ON gateway_usage_method_hourly (account_id, chain, network, bucket_hour)
    """,
    """
    CREATE FUNCTION gateway_usage_maintain_partitions(reference_at TIMESTAMPTZ, retention_months INTEGER)
    RETURNS TABLE(created_partitions INTEGER, dropped_partitions INTEGER)
    LANGUAGE plpgsql
    SET search_path FROM CURRENT
    AS $$
    DECLARE
        schema_name TEXT := current_schema();
        month_start DATE := date_trunc('month', reference_at AT TIME ZONE 'UTC')::date;
        retention_start DATE := month_start - make_interval(months => retention_months - 1);
        target_month DATE;
        next_month DATE;
        relation_name TEXT;
        child RECORD;
        created_count INTEGER := 0;
        dropped_count INTEGER := 0;
        offset_month INTEGER;
    BEGIN
        IF retention_months < 2 THEN
            RAISE EXCEPTION 'retention_months must preserve the previous month';
        END IF;

        FOR offset_month IN -1..1 LOOP
            target_month := month_start + make_interval(months => offset_month);
            next_month := target_month + make_interval(months => 1);

            relation_name := 'gateway_usage_hourly_' || to_char(target_month, 'YYYYMM');
            IF to_regclass(format('%I.%I', schema_name, relation_name)) IS NULL THEN
                EXECUTE format(
                    'CREATE TABLE %I.%I PARTITION OF %I.gateway_usage_hourly FOR VALUES FROM (%L) TO (%L)',
                    schema_name,
                    relation_name,
                    schema_name,
                    target_month::text || ' 00:00:00+00',
                    next_month::text || ' 00:00:00+00'
                );
                created_count := created_count + 1;
            END IF;

            relation_name := 'gateway_usage_method_hourly_' || to_char(target_month, 'YYYYMM');
            IF to_regclass(format('%I.%I', schema_name, relation_name)) IS NULL THEN
                EXECUTE format(
                    'CREATE TABLE %I.%I PARTITION OF %I.gateway_usage_method_hourly FOR VALUES FROM (%L) TO (%L)',
                    schema_name,
                    relation_name,
                    schema_name,
                    target_month::text || ' 00:00:00+00',
                    next_month::text || ' 00:00:00+00'
                );
                created_count := created_count + 1;
            END IF;
        END LOOP;

        FOR child IN
            SELECT child_class.relname
            FROM pg_inherits
            JOIN pg_class AS parent_class ON parent_class.oid = pg_inherits.inhparent
            JOIN pg_class AS child_class ON child_class.oid = pg_inherits.inhrelid
            JOIN pg_namespace AS child_namespace ON child_namespace.oid = child_class.relnamespace
            WHERE child_namespace.nspname = schema_name
              AND parent_class.relname IN ('gateway_usage_hourly', 'gateway_usage_method_hourly')
        LOOP
            IF to_date(substring(child.relname FROM '([0-9]{6})$'), 'YYYYMM') < retention_start THEN
                EXECUTE format('DROP TABLE %I.%I', schema_name, child.relname);
                dropped_count := dropped_count + 1;
            END IF;
        END LOOP;

        RETURN QUERY SELECT created_count, dropped_count;
    END
    $$
    """,
    'SELECT * FROM gateway_usage_maintain_partitions(CURRENT_TIMESTAMP, 18)',
]

REVERSE_SQL = [
    'DROP FUNCTION IF EXISTS gateway_usage_maintain_partitions(TIMESTAMPTZ, INTEGER)',
    'DROP TABLE IF EXISTS gateway_usage_method_hourly CASCADE',
    'DROP TABLE IF EXISTS gateway_usage_hourly CASCADE',
    'DROP TABLE IF EXISTS gateway_usage_checkpoint CASCADE',
    'DROP INDEX IF EXISTS uq_provider_active_account_name',
    'ALTER TABLE system_jsonrpc_cache_payload DROP CONSTRAINT IF EXISTS chk_system_jsonrpc_cache_payload_size',
    'ALTER TABLE endpoint DROP CONSTRAINT IF EXISTS chk_endpoint_auth_columns',
]


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='Account',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('email', fields.CharField(unique=True, max_length=320)),
                ('role', fields.CharEnumField(default=AccountRole.USER, description='ADMIN: admin\nUSER: user', enum_type=AccountRole, max_length=32)),
                ('status', fields.CharEnumField(default=AccountStatus.UNACTIVATED, description='UNACTIVATED: unactivated\nACTIVE: active\nDISABLED: disabled\nARCHIVED: archived', enum_type=AccountStatus, max_length=32)),
                ('password_hash', fields.CharField(null=True, max_length=255)),
                ('name', fields.CharField(null=True, max_length=255)),
                ('avatar_url', fields.CharField(null=True, max_length=1024)),
                ('first_login_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('last_login_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('last_login_ip', fields.CharField(null=True, max_length=64)),
                ('last_login_user_agent', fields.CharField(null=True, max_length=512)),
            ],
            options={'table': 'account', 'app': 'models', 'indexes': [Index(fields=['deleted_at', 'role', 'status', 'first_login_at', 'created_at'], name='idx_account_admin_list')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='App',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account', fields.ForeignKeyField('models.Account', source_field='account_id', db_constraint=True, to_field='id', related_name='apps', on_delete=OnDelete.CASCADE)),
                ('name', fields.CharField(max_length=128)),
                ('enabled', fields.BooleanField(default=True)),
                ('version', fields.IntField(default=1)),
            ],
            options={'table': 'app', 'app': 'models', 'indexes': [Index(fields=['account_id', 'deleted_at', 'created_at'], name='idx_app_account_created'), Index(fields=['account_id', 'deleted_at', 'enabled'], name='idx_app_account_enabled')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='AppApiKey',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('app', fields.ForeignKeyField('models.App', source_field='app_id', db_constraint=True, to_field='id', related_name='api_keys', on_delete=OnDelete.CASCADE)),
                ('api_key_digest', fields.CharField(unique=True, max_length=64)),
                ('encrypted_api_key', fields.TextField(unique=False)),
                ('expires_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('revoked_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'app_api_key', 'app': 'models', 'indexes': [Index(fields=['app_id', 'deleted_at', 'created_at'], name='idx_app_api_key_app_created')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='AppAuditEvent',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('app', fields.ForeignKeyField('models.App', source_field='app_id', db_constraint=True, to_field='id', related_name='audit_events', on_delete=OnDelete.CASCADE)),
                ('account_id', fields.CharField(max_length=21)),
                ('actor_id', fields.CharField(max_length=21)),
                ('resource_type', fields.CharField(max_length=32)),
                ('resource_id', fields.CharField(max_length=21)),
                ('action', fields.CharEnumField(description='CREATED: created\nUPDATED: updated\nDELETED: deleted\nAPI_KEY_CREATED: api_key_created\nAPI_KEY_REVEALED: api_key_revealed\nAPI_KEY_REVOKED: api_key_revoked', enum_type=AppAuditAction, max_length=32)),
                ('previous_version', fields.IntField(null=True)),
                ('new_version', fields.IntField(null=True)),
                ('changed_fields', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'app_audit_event', 'app': 'models', 'indexes': [Index(fields=['app_id', 'created_at'], name='idx_app_audit_app_created'), Index(fields=['account_id', 'created_at'], name='idx_app_audit_account_created')], 'pk_attr': 'id'},
            bases=['GuidMixin'],
        ),
        ops.CreateModel(
            name='Auth',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account', fields.ForeignKeyField('models.Account', source_field='account_id', db_constraint=True, to_field='id', related_name='auths', on_delete=OnDelete.CASCADE)),
                ('provider', fields.CharEnumField(description='GOOGLE: google', enum_type=AuthProvider, max_length=32)),
                ('identifier', fields.CharField(max_length=320)),
            ],
            options={'table': 'auth', 'app': 'models', 'unique_together': (('provider', 'identifier'),), 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='AuthSession',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account', fields.ForeignKeyField('models.Account', source_field='account_id', db_constraint=True, to_field='id', related_name='auth_sessions', on_delete=OnDelete.CASCADE)),
                ('token_hash', fields.CharField(unique=True, max_length=128)),
                ('expires_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('revoked_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'auth_session', 'app': 'models', 'indexes': [Index(fields=['account_id', 'deleted_at', 'revoked_at'], name='idx_auth_session_account')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='Endpoint',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account', fields.ForeignKeyField('models.Account', source_field='account_id', db_constraint=True, to_field='id', related_name='endpoints', on_delete=OnDelete.CASCADE)),
                ('name', fields.CharField(max_length=128)),
                ('chain', fields.CharEnumField(description='ETHEREUM: ethereum\nPOLYGON: polygon\nBSC: bsc\nARBITRUM: arbitrum\nOPTIMISM: optimism\nBASE: base\nSOLANA: solana\nBITCOIN: bitcoin\nLITECOIN: litecoin\nTRON: tron', enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(description='MAINNET: mainnet\nMAINNET_BETA: mainnet-beta\nSEPOLIA: sepolia\nAMOY: amoy\nTESTNET: testnet\nDEVNET: devnet\nNILE: nile', enum_type=Network, max_length=32)),
                ('protocol', fields.CharEnumField(description='JSONRPC: jsonrpc\nHTTP_API: http_api', enum_type=EndpointProtocol, max_length=32)),
                ('encrypted_url', fields.TextField(unique=False)),
                ('enabled', fields.BooleanField(default=True)),
                ('trust_level', fields.CharEnumField(default=EndpointTrustLevel.UNVERIFIED, description='UNVERIFIED: unverified\nTRUSTED: trusted\nAUTHORITATIVE: authoritative', enum_type=EndpointTrustLevel, max_length=32)),
                ('auth_type', fields.CharEnumField(default=EndpointAuthType.NONE, description='NONE: none\nBEARER: bearer\nHEADER_API_KEY: header_api_key\nQUERY_API_KEY: query_api_key\nPATH_API_KEY: path_api_key', enum_type=EndpointAuthType, max_length=32)),
                ('auth_header_name', fields.CharField(null=True, max_length=128)),
                ('auth_query_param', fields.CharField(null=True, max_length=128)),
                ('encrypted_auth_secret', fields.TextField(null=True, unique=False)),
                ('version', fields.IntField(default=1)),
            ],
            options={'table': 'endpoint', 'app': 'models', 'unique_together': (('account', 'name'),), 'constraints': [CheckConstraint(check="\n(\n    auth_type = 'none'\n    AND auth_header_name IS NULL\n    AND auth_query_param IS NULL\n    AND encrypted_auth_secret IS NULL\n)\nOR (\n    auth_type IN ('bearer', 'path_api_key')\n    AND auth_header_name IS NULL\n    AND auth_query_param IS NULL\n    AND encrypted_auth_secret IS NOT NULL\n)\nOR (\n    auth_type = 'header_api_key'\n    AND NULLIF(BTRIM(auth_header_name), '') IS NOT NULL\n    AND auth_query_param IS NULL\n    AND encrypted_auth_secret IS NOT NULL\n)\nOR (\n    auth_type = 'query_api_key'\n    AND auth_header_name IS NULL\n    AND NULLIF(BTRIM(auth_query_param), '') IS NOT NULL\n    AND encrypted_auth_secret IS NOT NULL\n)\n", name='chk_endpoint_auth_columns')], 'indexes': [Index(fields=['account_id', 'deleted_at', 'chain', 'network', 'protocol', 'enabled'], name='idx_endpoint_account_filters'), Index(fields=['account_id', 'deleted_at', 'created_at'], name='idx_endpoint_account_order')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='EndpointAuditEvent',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('endpoint', fields.ForeignKeyField('models.Endpoint', source_field='endpoint_id', db_constraint=True, to_field='id', related_name='audit_events', on_delete=OnDelete.CASCADE)),
                ('account_id', fields.CharField(max_length=21)),
                ('actor_id', fields.CharField(max_length=21)),
                ('action', fields.CharEnumField(description='CREATED: created\nUPDATED: updated\nDELETED: deleted\nARCHIVED: archived\nRESTORED: restored', enum_type=EndpointAuditAction, max_length=32)),
                ('previous_version', fields.IntField(null=True)),
                ('new_version', fields.IntField()),
                ('changed_fields', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'endpoint_audit_event', 'app': 'models', 'indexes': [Index(fields=['endpoint_id', 'account_id', 'created_at'], name='idx_endpoint_audit_endpoint_order'), Index(fields=['account_id', 'created_at'], name='idx_endpoint_audit_account_order')], 'pk_attr': 'id'},
            bases=['GuidMixin'],
        ),
        ops.CreateModel(
            name='Gateway',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('app', fields.ForeignKeyField('models.App', source_field='app_id', db_constraint=True, to_field='id', related_name='gateways', on_delete=OnDelete.CASCADE)),
                ('name', fields.CharField(max_length=128)),
                ('chain', fields.CharEnumField(description='ETHEREUM: ethereum\nPOLYGON: polygon\nBSC: bsc\nARBITRUM: arbitrum\nOPTIMISM: optimism\nBASE: base\nSOLANA: solana\nBITCOIN: bitcoin\nLITECOIN: litecoin\nTRON: tron', enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(description='MAINNET: mainnet\nMAINNET_BETA: mainnet-beta\nSEPOLIA: sepolia\nAMOY: amoy\nTESTNET: testnet\nDEVNET: devnet\nNILE: nile', enum_type=Network, max_length=32)),
                ('transport_types', fields.JSONField(encoder=JSON_DUMPS, decoder=loads)),
                ('enabled', fields.BooleanField(default=True)),
                ('version', fields.IntField(default=1)),
            ],
            options={'table': 'gateway', 'app': 'models', 'unique_together': (('app', 'chain', 'network'),), 'indexes': [Index(fields=['app_id', 'deleted_at', 'created_at'], name='idx_gateway_app_created'), Index(fields=['app_id', 'deleted_at', 'enabled'], name='idx_gateway_app_enabled'), Index(fields=['deleted_at', 'chain', 'network', 'enabled'], name='idx_gateway_chain_network')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='HttpApiRateLimitPolicy',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('name', fields.CharField(unique=True, max_length=64)),
                ('mode', fields.CharEnumField(default=AdmissionMode.SHADOW, description='DISABLED: disabled\nSHADOW: shadow\nENFORCE: enforce', enum_type=AdmissionMode, max_length=16)),
                ('max_inflight_per_worker', fields.IntField(default=64)),
                ('redis_timeout_ms', fields.IntField(default=50)),
                ('redis_admission_per_worker', fields.IntField(default=128)),
                ('fallback_max_keys_per_worker', fields.IntField(default=50000)),
                ('global_rps', fields.IntField(default=500)),
                ('global_burst', fields.IntField(default=1000)),
                ('ip_rps', fields.IntField(default=100)),
                ('ip_burst', fields.IntField(default=200)),
                ('account_rps', fields.IntField(default=50)),
                ('account_burst', fields.IntField(default=100)),
                ('app_rps', fields.IntField(default=25)),
                ('app_burst', fields.IntField(default=50)),
                ('version', fields.IntField(default=1)),
                ('modified_by_account_id', fields.CharField(null=True, max_length=21)),
            ],
            options={'table': 'http_api_rate_limit_policy', 'app': 'models', 'indexes': [Index(fields=['deleted_at', 'name'], name='idx_http_api_rate_limit_policy_name')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='HttpApiRateLimitAuditEvent',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('policy', fields.ForeignKeyField('models.HttpApiRateLimitPolicy', source_field='policy_id', db_constraint=True, to_field='id', related_name='audit_events', on_delete=OnDelete.CASCADE)),
                ('actor_id', fields.CharField(max_length=21)),
                ('previous_version', fields.IntField()),
                ('new_version', fields.IntField()),
                ('changed_fields', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
            ],
            options={'table': 'http_api_rate_limit_policy_audit_event', 'app': 'models', 'indexes': [Index(fields=['policy_id', 'created_at'], name='idx_http_api_rate_limit_audit_policy')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='HttpApiRoute',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('gateway', fields.ForeignKeyField('models.Gateway', source_field='gateway_id', db_constraint=True, to_field='id', related_name='http_api_routes', on_delete=OnDelete.CASCADE)),
                ('strategy_type', fields.CharEnumField(default=HttpApiRoutingStrategyType.LOAD_BALANCE, description='LOAD_BALANCE: load_balance\nPRIORITY_FAILOVER: priority_failover', enum_type=HttpApiRoutingStrategyType, max_length=32)),
                ('minimum_trust', fields.CharEnumField(default=EndpointTrustLevel.UNVERIFIED, description='UNVERIFIED: unverified\nTRUSTED: trusted\nAUTHORITATIVE: authoritative', enum_type=EndpointTrustLevel, max_length=32)),
                ('max_latency_ms', fields.FloatField(null=True)),
                ('max_attempts', fields.IntField(default=3)),
                ('retry_policy', fields.CharEnumField(default=HttpApiRetryPolicy.SAFE_ONLY, description='SAFE_ONLY: safe_only\nIDEMPOTENT: idempotent', enum_type=HttpApiRetryPolicy, max_length=32)),
                ('version', fields.IntField(default=1)),
            ],
            options={'table': 'http_api_route', 'app': 'models', 'unique_together': (('gateway',),), 'indexes': [Index(fields=['gateway_id', 'deleted_at'], name='idx_http_api_route_gateway')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='HttpApiRouteTarget',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('route', fields.ForeignKeyField('models.HttpApiRoute', source_field='route_id', db_constraint=True, to_field='id', related_name='targets', on_delete=OnDelete.CASCADE)),
                ('endpoint', fields.ForeignKeyField('models.Endpoint', source_field='endpoint_id', db_constraint=True, to_field='id', related_name='http_api_route_targets', on_delete=OnDelete.RESTRICT)),
                ('position', fields.IntField()),
                ('weight', fields.IntField(null=True)),
            ],
            options={'table': 'http_api_route_target', 'app': 'models', 'unique_together': (('route', 'endpoint'), ('route', 'position')), 'indexes': [Index(fields=['endpoint_id', 'deleted_at'], name='idx_http_api_route_target_endpoint')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='JsonRpcRateLimitPolicy',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('name', fields.CharField(unique=True, max_length=64)),
                ('mode', fields.CharEnumField(default=AdmissionMode.SHADOW, description='DISABLED: disabled\nSHADOW: shadow\nENFORCE: enforce', enum_type=AdmissionMode, max_length=16)),
                ('max_inflight_per_worker', fields.IntField(default=64)),
                ('redis_timeout_ms', fields.IntField(default=50)),
                ('redis_admission_per_worker', fields.IntField(default=128)),
                ('fallback_max_keys_per_worker', fields.IntField(default=50000)),
                ('global_rps', fields.IntField(default=500)),
                ('global_burst', fields.IntField(default=1000)),
                ('ip_rps', fields.IntField(default=100)),
                ('ip_burst', fields.IntField(default=200)),
                ('account_rps', fields.IntField(default=50)),
                ('account_burst', fields.IntField(default=100)),
                ('app_rps', fields.IntField(default=25)),
                ('app_burst', fields.IntField(default=50)),
                ('version', fields.IntField(default=1)),
                ('modified_by_account_id', fields.CharField(null=True, max_length=21)),
            ],
            options={'table': 'jsonrpc_rate_limit_policy', 'app': 'models', 'indexes': [Index(fields=['deleted_at', 'name'], name='idx_jsonrpc_rate_limit_policy_name')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='JsonRpcRateLimitAuditEvent',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('policy', fields.ForeignKeyField('models.JsonRpcRateLimitPolicy', source_field='policy_id', db_constraint=True, to_field='id', related_name='audit_events', on_delete=OnDelete.CASCADE)),
                ('actor_id', fields.CharField(max_length=21)),
                ('previous_version', fields.IntField()),
                ('new_version', fields.IntField()),
                ('changed_fields', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
            ],
            options={'table': 'jsonrpc_rate_limit_policy_audit_event', 'app': 'models', 'indexes': [Index(fields=['policy_id', 'created_at'], name='idx_jsonrpc_rate_limit_audit_policy')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='JsonRpcRoute',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('gateway', fields.ForeignKeyField('models.Gateway', source_field='gateway_id', db_constraint=True, to_field='id', related_name='jsonrpc_routes', on_delete=OnDelete.CASCADE)),
                ('strategy_type', fields.CharEnumField(default=JsonRpcRoutingStrategyType.LOAD_BALANCE, description='LOAD_BALANCE: load_balance\nPRIORITY_FAILOVER: priority_failover', enum_type=JsonRpcRoutingStrategyType, max_length=32)),
                ('minimum_trust', fields.CharEnumField(default=EndpointTrustLevel.UNVERIFIED, description='UNVERIFIED: unverified\nTRUSTED: trusted\nAUTHORITATIVE: authoritative', enum_type=EndpointTrustLevel, max_length=32)),
                ('max_latency_ms', fields.FloatField(null=True)),
                ('max_attempts', fields.IntField(default=3)),
                ('retry_policy', fields.CharEnumField(default=JsonRpcRetryPolicy.SAFE_ONLY, description='SAFE_ONLY: safe_only\nIDEMPOTENT: idempotent', enum_type=JsonRpcRetryPolicy, max_length=32)),
                ('version', fields.IntField(default=1)),
            ],
            options={'table': 'jsonrpc_route', 'app': 'models', 'indexes': [Index(fields=['gateway_id', 'deleted_at', 'created_at'], name='idx_jsonrpc_route_gateway_created')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='JsonRpcRouteScope',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('route', fields.ForeignKeyField('models.JsonRpcRoute', source_field='route_id', db_constraint=True, to_field='id', related_name='scopes', on_delete=OnDelete.CASCADE)),
                ('gateway', fields.ForeignKeyField('models.Gateway', source_field='gateway_id', db_constraint=True, to_field='id', related_name='jsonrpc_route_scopes', on_delete=OnDelete.CASCADE)),
                ('method', fields.CharField(max_length=256)),
            ],
            options={'table': 'jsonrpc_route_scope', 'app': 'models', 'unique_together': (('gateway', 'method'),), 'indexes': [Index(fields=['route_id', 'method'], name='idx_jsonrpc_route_scope_route_method')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='JsonRpcRouteTarget',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('route', fields.ForeignKeyField('models.JsonRpcRoute', source_field='route_id', db_constraint=True, to_field='id', related_name='targets', on_delete=OnDelete.CASCADE)),
                ('endpoint', fields.ForeignKeyField('models.Endpoint', source_field='endpoint_id', db_constraint=True, to_field='id', related_name='jsonrpc_route_targets', on_delete=OnDelete.RESTRICT)),
                ('position', fields.IntField()),
                ('weight', fields.IntField(null=True)),
            ],
            options={'table': 'jsonrpc_route_target', 'app': 'models', 'unique_together': (('route', 'endpoint'), ('route', 'position')), 'indexes': [Index(fields=['endpoint_id', 'deleted_at'], name='idx_jsonrpc_route_target_endpoint')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='Provider',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account', fields.ForeignKeyField('models.Account', source_field='account_id', db_constraint=True, to_field='id', related_name='providers', on_delete=OnDelete.CASCADE)),
                ('name', fields.CharField(max_length=128)),
                ('vendor', fields.CharEnumField(description='ALCHEMY: alchemy\nQUICKNODE: quicknode\nCHAINSTACK: chainstack\nDRPC: drpc\nTENDERLY: tenderly', enum_type=ProviderVendor, max_length=32)),
                ('enabled', fields.BooleanField(default=True)),
                ('sync_enabled', fields.BooleanField(default=False)),
                ('sync_interval_seconds', fields.IntField(default=86400)),
                ('encrypted_credential', fields.TextField(unique=False)),
                ('settings', fields.JSONField(default=dict, encoder=JSON_DUMPS, decoder=loads)),
                ('only_networks', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
                ('ignore_networks', fields.JSONField(default=list, encoder=JSON_DUMPS, decoder=loads)),
                ('last_sync_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('last_sync_status', fields.CharEnumField(default=ProviderSyncStatus.NEVER, description='NEVER: never\nSUCCESS: success\nPARTIAL: partial\nFAILED: failed', enum_type=ProviderSyncStatus, max_length=32)),
                ('last_sync_error', fields.TextField(null=True, unique=False)),
                ('last_sync_created', fields.IntField(default=0)),
                ('last_sync_updated', fields.IntField(default=0)),
                ('last_sync_restored', fields.IntField(default=0)),
                ('last_sync_archived', fields.IntField(default=0)),
                ('last_sync_skipped', fields.IntField(default=0)),
                ('version', fields.IntField(default=1)),
            ],
            options={'table': 'provider', 'app': 'models', 'constraints': [UniqueConstraint(fields=('account', 'name'), name='uq_provider_active_account_name', condition='deleted_at IS NULL')], 'indexes': [Index(fields=['account_id', 'deleted_at', 'vendor', 'enabled'], name='idx_provider_account_vendor'), Index(fields=['account_id', 'deleted_at', 'created_at'], name='idx_provider_account_order'), Index(fields=['deleted_at', 'enabled', 'sync_enabled', 'last_sync_at'], name='idx_provider_sync_due')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='ProviderEndpointBinding',
            fields=[
                ('endpoint', fields.OneToOneField('models.Endpoint', source_field='endpoint_id', primary_key=True, db_index=True, db_constraint=True, to_field='id', related_name='provider_binding', on_delete=OnDelete.CASCADE)),
                ('provider', fields.ForeignKeyField('models.Provider', source_field='provider_id', db_constraint=True, to_field='id', related_name='endpoint_bindings', on_delete=OnDelete.RESTRICT)),
                ('external_id', fields.CharField(max_length=512)),
                ('last_seen_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'provider_endpoint_binding', 'app': 'models', 'unique_together': (('provider', 'external_id'),), 'pk_attr': 'endpoint_id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='SystemJsonRpcCachePayload',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('chain', fields.CharEnumField(description='ETHEREUM: ethereum\nPOLYGON: polygon\nBSC: bsc\nARBITRUM: arbitrum\nOPTIMISM: optimism\nBASE: base\nSOLANA: solana\nBITCOIN: bitcoin\nLITECOIN: litecoin\nTRON: tron', enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(description='MAINNET: mainnet\nMAINNET_BETA: mainnet-beta\nSEPOLIA: sepolia\nAMOY: amoy\nTESTNET: testnet\nDEVNET: devnet\nNILE: nile', enum_type=Network, max_length=32)),
                ('method', fields.CharField(max_length=256)),
                ('cache_key', fields.CharField(max_length=40)),
                ('sequence', fields.BigIntField(null=True)),
                ('payload', fields.BinaryField()),
                ('payload_size', fields.IntField()),
                ('fresh_until', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('stale_until', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('publisher_fence', fields.BigIntField(default=0)),
                ('stored_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'system_jsonrpc_cache_payload', 'app': 'models', 'unique_together': (('chain', 'network', 'method', 'cache_key'),), 'constraints': [CheckConstraint(check='payload_size = octet_length(payload)', name='chk_system_jsonrpc_cache_payload_size')], 'indexes': [Index(fields=['chain', 'stored_at'], name='idx_system_jsonrpc_cache_payload_retention')], 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='SystemJsonRpcCachePayloadLease',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('chain', fields.CharEnumField(description='ETHEREUM: ethereum\nPOLYGON: polygon\nBSC: bsc\nARBITRUM: arbitrum\nOPTIMISM: optimism\nBASE: base\nSOLANA: solana\nBITCOIN: bitcoin\nLITECOIN: litecoin\nTRON: tron', enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(description='MAINNET: mainnet\nMAINNET_BETA: mainnet-beta\nSEPOLIA: sepolia\nAMOY: amoy\nTESTNET: testnet\nDEVNET: devnet\nNILE: nile', enum_type=Network, max_length=32)),
                ('method', fields.CharField(max_length=256)),
                ('cache_key', fields.CharField(max_length=40)),
                ('token', fields.CharField(max_length=64)),
                ('fence', fields.BigIntField()),
                ('lease_until', fields.DatetimeField(auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'system_jsonrpc_cache_payload_lease', 'app': 'models', 'unique_together': (('chain', 'network', 'method', 'cache_key'),), 'indexes': [Index(fields=['chain', 'lease_until'], name='idx_system_jsonrpc_cache_payload_lease_expiry')], 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.AlterModelOptions(
            name='ProviderEndpointBinding',
            options={'table': 'provider_endpoint_binding', 'app': 'models', 'unique_together': (('provider', 'external_id'),), 'pk_attr': 'endpoint_id'},
        ),
        PartitionedUsageState(),
        ops.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
