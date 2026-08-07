# ruff: noqa: E501, I001
# pyright: reportArgumentType=false, reportAssignmentType=false
# fmt: off
# Reason: Tortoise migration values and layout are generated for stable schema-state serialization.

from tortoise import migrations
from tortoise.migrations import operations as ops
import app.orm.mixin
from app.model.blockchain import Chain, Network
from app.orm.mixin import NANOIDField
from tortoise import fields
from tortoise.indexes import Index
from tortoise.migrations.constraints import CheckConstraint
from tortoise.migrations.schema_editor.base import BaseSchemaEditor
from tortoise.migrations.schema_generator.state import State

_FINE_USAGE_STATE_OPERATIONS = [
        ops.CreateModel(
            name='GatewayUsageFiveMinute',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account_id', fields.CharField(max_length=21)),
                ('app_id', fields.CharField(max_length=21)),
                ('gateway_id', fields.CharField(max_length=21)),
                ('chain', fields.CharEnumField(description='ETHEREUM: ethereum\nPOLYGON: polygon\nBSC: bsc\nARBITRUM: arbitrum\nOPTIMISM: optimism\nBASE: base\nSOLANA: solana\nBITCOIN: bitcoin\nLITECOIN: litecoin\nTRON: tron', enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(description='MAINNET: mainnet\nMAINNET_BETA: mainnet-beta\nSEPOLIA: sepolia\nAMOY: amoy\nTESTNET: testnet\nDEVNET: devnet\nNILE: nile', enum_type=Network, max_length=32)),
                ('bucket_start', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('total_requests', fields.BigIntField(default=0)),
                ('successful_requests', fields.BigIntField(default=0)),
                ('failed_requests', fields.BigIntField(default=0)),
                ('total_duration_ms', fields.BigIntField(default=0)),
                ('total_request_bytes', fields.BigIntField(default=0)),
                ('total_response_bytes', fields.BigIntField(default=0)),
                ('cache_eligible_requests', fields.BigIntField(default=0)),
                ('cache_hit_requests', fields.BigIntField(default=0)),
            ],
            options={'table': 'gateway_usage_five_minute', 'app': 'models', 'unique_together': (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'bucket_start'),), 'constraints': [CheckConstraint(check='\n    total_requests >= 0\n    AND successful_requests >= 0\n    AND failed_requests >= 0\n    AND total_duration_ms >= 0\n    AND total_request_bytes >= 0\n    AND total_response_bytes >= 0\n    AND cache_eligible_requests >= 0\n    AND cache_hit_requests >= 0\n', name='chk_gateway_usage_five_minute_nonnegative'), CheckConstraint(check='successful_requests + failed_requests = total_requests', name='chk_gateway_usage_five_minute_outcomes'), CheckConstraint(check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests', name='chk_gateway_usage_five_minute_cache')], 'indexes': [Index(fields=['account_id', 'bucket_start'], name='idx_gateway_usage_five_minute_account_bucket'), Index(fields=['account_id', 'app_id', 'bucket_start'], name='idx_gateway_usage_five_minute_account_app_bucket'), Index(fields=['account_id', 'gateway_id', 'bucket_start'], name='idx_gateway_usage_five_minute_account_gateway_bucket'), Index(fields=['account_id', 'chain', 'network', 'bucket_start'], name='idx_gateway_usage_five_minute_account_network_bucket')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
        ops.CreateModel(
            name='GatewayUsageMethodFiveMinute',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('account_id', fields.CharField(max_length=21)),
                ('app_id', fields.CharField(max_length=21)),
                ('gateway_id', fields.CharField(max_length=21)),
                ('chain', fields.CharEnumField(description='ETHEREUM: ethereum\nPOLYGON: polygon\nBSC: bsc\nARBITRUM: arbitrum\nOPTIMISM: optimism\nBASE: base\nSOLANA: solana\nBITCOIN: bitcoin\nLITECOIN: litecoin\nTRON: tron', enum_type=Chain, max_length=32)),
                ('network', fields.CharEnumField(description='MAINNET: mainnet\nMAINNET_BETA: mainnet-beta\nSEPOLIA: sepolia\nAMOY: amoy\nTESTNET: testnet\nDEVNET: devnet\nNILE: nile', enum_type=Network, max_length=32)),
                ('method', fields.CharField(max_length=256)),
                ('bucket_start', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('total_requests', fields.BigIntField(default=0)),
                ('successful_requests', fields.BigIntField(default=0)),
                ('failed_requests', fields.BigIntField(default=0)),
                ('total_duration_ms', fields.BigIntField(default=0)),
                ('total_request_bytes', fields.BigIntField(default=0)),
                ('total_response_bytes', fields.BigIntField(default=0)),
                ('cache_eligible_requests', fields.BigIntField(default=0)),
                ('cache_hit_requests', fields.BigIntField(default=0)),
            ],
            options={'table': 'gateway_usage_method_five_minute', 'app': 'models', 'unique_together': (('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'method', 'bucket_start'),), 'constraints': [CheckConstraint(check='\n    total_requests >= 0\n    AND successful_requests >= 0\n    AND failed_requests >= 0\n    AND total_duration_ms >= 0\n    AND total_request_bytes >= 0\n    AND total_response_bytes >= 0\n    AND cache_eligible_requests >= 0\n    AND cache_hit_requests >= 0\n', name='chk_gateway_usage_method_five_minute_nonnegative'), CheckConstraint(check='successful_requests + failed_requests = total_requests', name='chk_gateway_usage_method_five_minute_outcomes'), CheckConstraint(check='cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests', name='chk_gateway_usage_method_five_minute_cache')], 'indexes': [Index(fields=['account_id', 'bucket_start'], name='idx_gateway_usage_method_five_minute_account_bucket'), Index(fields=['account_id', 'app_id', 'bucket_start'], name='idx_gateway_usage_method_five_minute_account_app_bucket'), Index(fields=['account_id', 'gateway_id', 'bucket_start'], name='idx_gateway_usage_method_five_minute_account_gateway_bucket'), Index(fields=['account_id', 'chain', 'network', 'bucket_start'], name='idx_gateway_usage_method_five_minute_account_network_bucket')], 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        ),
]

_ROLLUP_OPERATION = ops.CreateModel(
            name='GatewayUsageRollupHour',
            fields=[
                ('id', NANOIDField(primary_key=True, default=app.orm.mixin.NANOIDField.nanoid, unique=True, db_index=True)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('modified_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ('deleted_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('bucket_hour', fields.DatetimeField(unique=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'gateway_usage_rollup_hour', 'app': 'models', 'pk_attr': 'id'},
            bases=['GuidMixin', 'TimestampMixin'],
        )


class PartitionedFineUsageState(ops.TortoiseOperation):
    """Track the partitioned fine usage tables without creating ordinary ORM tables."""

    reduces_to_sql = False

    def state_forward(self, app_label: str, state: State) -> None:
        for operation in _FINE_USAGE_STATE_OPERATIONS:
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
    CREATE TABLE gateway_usage_five_minute (
        id CHAR(21) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ,
        account_id VARCHAR(21) NOT NULL,
        app_id VARCHAR(21) NOT NULL,
        gateway_id VARCHAR(21) NOT NULL,
        chain VARCHAR(32) NOT NULL,
        network VARCHAR(32) NOT NULL,
        bucket_start TIMESTAMPTZ NOT NULL,
        total_requests BIGINT NOT NULL DEFAULT 0,
        successful_requests BIGINT NOT NULL DEFAULT 0,
        failed_requests BIGINT NOT NULL DEFAULT 0,
        total_duration_ms BIGINT NOT NULL DEFAULT 0,
        total_request_bytes BIGINT NOT NULL DEFAULT 0,
        total_response_bytes BIGINT NOT NULL DEFAULT 0,
        cache_eligible_requests BIGINT NOT NULL DEFAULT 0,
        cache_hit_requests BIGINT NOT NULL DEFAULT 0,
        CONSTRAINT uq_gateway_usage_five_minute_scope
            UNIQUE (account_id, app_id, gateway_id, chain, network, bucket_start),
        CONSTRAINT chk_gateway_usage_five_minute_bucket CHECK (
            EXTRACT(MINUTE FROM bucket_start)::INTEGER % 5 = 0
            AND EXTRACT(SECOND FROM bucket_start) = 0
        ),
        CONSTRAINT chk_gateway_usage_five_minute_nonnegative CHECK (
            total_requests >= 0 AND successful_requests >= 0 AND failed_requests >= 0
            AND total_duration_ms >= 0 AND total_request_bytes >= 0 AND total_response_bytes >= 0
            AND cache_eligible_requests >= 0 AND cache_hit_requests >= 0
        ),
        CONSTRAINT chk_gateway_usage_five_minute_outcomes CHECK (
            successful_requests + failed_requests = total_requests
        ),
        CONSTRAINT chk_gateway_usage_five_minute_cache CHECK (
            cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests
        )
    ) PARTITION BY RANGE (bucket_start)
    """,
    """
    CREATE TABLE gateway_usage_method_five_minute (
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
        bucket_start TIMESTAMPTZ NOT NULL,
        total_requests BIGINT NOT NULL DEFAULT 0,
        successful_requests BIGINT NOT NULL DEFAULT 0,
        failed_requests BIGINT NOT NULL DEFAULT 0,
        total_duration_ms BIGINT NOT NULL DEFAULT 0,
        total_request_bytes BIGINT NOT NULL DEFAULT 0,
        total_response_bytes BIGINT NOT NULL DEFAULT 0,
        cache_eligible_requests BIGINT NOT NULL DEFAULT 0,
        cache_hit_requests BIGINT NOT NULL DEFAULT 0,
        CONSTRAINT uq_gateway_usage_method_five_minute_scope
            UNIQUE (account_id, app_id, gateway_id, chain, network, method, bucket_start),
        CONSTRAINT chk_gateway_usage_method_five_minute_bucket CHECK (
            EXTRACT(MINUTE FROM bucket_start)::INTEGER % 5 = 0
            AND EXTRACT(SECOND FROM bucket_start) = 0
        ),
        CONSTRAINT chk_gateway_usage_method_five_minute_nonnegative CHECK (
            total_requests >= 0 AND successful_requests >= 0 AND failed_requests >= 0
            AND total_duration_ms >= 0 AND total_request_bytes >= 0 AND total_response_bytes >= 0
            AND cache_eligible_requests >= 0 AND cache_hit_requests >= 0
        ),
        CONSTRAINT chk_gateway_usage_method_five_minute_outcomes CHECK (
            successful_requests + failed_requests = total_requests
        ),
        CONSTRAINT chk_gateway_usage_method_five_minute_cache CHECK (
            cache_hit_requests <= cache_eligible_requests AND cache_eligible_requests <= total_requests
        )
    ) PARTITION BY RANGE (bucket_start)
    """,
    'CREATE INDEX idx_gateway_usage_five_minute_account_bucket ON gateway_usage_five_minute (account_id, bucket_start)',
    'CREATE INDEX idx_gateway_usage_five_minute_account_app_bucket ON gateway_usage_five_minute (account_id, app_id, bucket_start)',
    'CREATE INDEX idx_gateway_usage_five_minute_account_gateway_bucket ON gateway_usage_five_minute (account_id, gateway_id, bucket_start)',
    'CREATE INDEX idx_gateway_usage_five_minute_account_network_bucket ON gateway_usage_five_minute (account_id, chain, network, bucket_start)',
    'CREATE INDEX idx_gateway_usage_method_five_minute_account_bucket ON gateway_usage_method_five_minute (account_id, bucket_start)',
    'CREATE INDEX idx_gateway_usage_method_five_minute_account_app_bucket ON gateway_usage_method_five_minute (account_id, app_id, bucket_start)',
    'CREATE INDEX idx_gateway_usage_method_five_minute_account_gateway_bucket ON gateway_usage_method_five_minute (account_id, gateway_id, bucket_start)',
    'CREATE INDEX idx_gateway_usage_method_five_minute_account_network_bucket ON gateway_usage_method_five_minute (account_id, chain, network, bucket_start)',
    """
    CREATE FUNCTION gateway_usage_fine_maintain_partitions(reference_at TIMESTAMPTZ, retention_hours INTEGER)
    RETURNS TABLE(created_partitions INTEGER, dropped_partitions INTEGER)
    LANGUAGE plpgsql
    SET search_path FROM CURRENT
    AS $$
    DECLARE
        schema_name TEXT := current_schema();
        retention_day DATE := ((reference_at - make_interval(hours => retention_hours)) AT TIME ZONE 'UTC')::date;
        last_day DATE := (reference_at AT TIME ZONE 'UTC')::date + 1;
        target_day DATE;
        next_day DATE;
        relation_name TEXT;
        child RECORD;
        child_day DATE;
        created_count INTEGER := 0;
        dropped_count INTEGER := 0;
    BEGIN
        IF retention_hours < 24 THEN
            RAISE EXCEPTION 'retention_hours must be at least 24';
        END IF;

        target_day := retention_day;
        WHILE target_day <= last_day LOOP
            next_day := target_day + 1;
            relation_name := 'gateway_usage_five_minute_' || to_char(target_day, 'YYYYMMDD');
            IF to_regclass(format('%I.%I', schema_name, relation_name)) IS NULL THEN
                EXECUTE format(
                    'CREATE TABLE %I.%I PARTITION OF %I.gateway_usage_five_minute FOR VALUES FROM (%L) TO (%L)',
                    schema_name, relation_name, schema_name,
                    target_day::text || ' 00:00:00+00', next_day::text || ' 00:00:00+00'
                );
                created_count := created_count + 1;
            END IF;
            relation_name := 'gateway_usage_method_five_minute_' || to_char(target_day, 'YYYYMMDD');
            IF to_regclass(format('%I.%I', schema_name, relation_name)) IS NULL THEN
                EXECUTE format(
                    'CREATE TABLE %I.%I PARTITION OF %I.gateway_usage_method_five_minute FOR VALUES FROM (%L) TO (%L)',
                    schema_name, relation_name, schema_name,
                    target_day::text || ' 00:00:00+00', next_day::text || ' 00:00:00+00'
                );
                created_count := created_count + 1;
            END IF;
            target_day := next_day;
        END LOOP;

        FOR child IN
            SELECT child_class.relname
            FROM pg_inherits
            JOIN pg_class AS parent_class ON parent_class.oid = pg_inherits.inhparent
            JOIN pg_class AS child_class ON child_class.oid = pg_inherits.inhrelid
            JOIN pg_namespace AS child_namespace ON child_namespace.oid = child_class.relnamespace
            WHERE child_namespace.nspname = schema_name
              AND parent_class.relname IN ('gateway_usage_five_minute', 'gateway_usage_method_five_minute')
        LOOP
            child_day := to_date(substring(child.relname FROM '([0-9]{8})$'), 'YYYYMMDD');
            IF child_day < retention_day AND NOT EXISTS (
                SELECT 1 FROM gateway_usage_rollup_hour
                WHERE bucket_hour >= child_day::timestamp AT TIME ZONE 'UTC'
                  AND bucket_hour < (child_day + 1)::timestamp AT TIME ZONE 'UTC'
                  AND deleted_at IS NULL
            ) THEN
                EXECUTE format('DROP TABLE %I.%I', schema_name, child.relname);
                dropped_count := dropped_count + 1;
            END IF;
        END LOOP;

        RETURN QUERY SELECT created_count, dropped_count;
    END
    $$
    """,
    'SELECT * FROM gateway_usage_fine_maintain_partitions(CURRENT_TIMESTAMP, 48)',
]

REVERSE_SQL = [
    'DROP FUNCTION IF EXISTS gateway_usage_fine_maintain_partitions(TIMESTAMPTZ, INTEGER)',
    'DROP TABLE IF EXISTS gateway_usage_method_five_minute CASCADE',
    'DROP TABLE IF EXISTS gateway_usage_five_minute CASCADE',
]


class Migration(migrations.Migration):
    dependencies = [('models', '0001_initial')]

    initial = False

    operations = [
        _ROLLUP_OPERATION,
        PartitionedFineUsageState(),
        ops.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
