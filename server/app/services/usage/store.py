from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from tortoise import connections
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.expressions import Q

from app.core.config import CONF
from app.infra.db import in_tx
from app.orm.mixin import NANOIDField
from app.orm.usage import GatewayUsageCheckpoint, GatewayUsageMethodFiveMinute, GatewayUsageMethodHourly

UsageScope = tuple[str, str, str, str, str, datetime]
UsageFineScope = tuple[str, str, str, str, str, datetime]
UsageFineMethodKey = tuple[str, str, str, str, str, str, datetime]
UsageEndpointKey = tuple[str, str, str, str, str, str, str, datetime]
UsageRouteKey = tuple[str, str, str, str, str, str, datetime]

ACTIVATE_ROUTE_AWARE_METRICS_SQL: Final[str] = """
UPDATE gateway_usage_metric_availability
SET coverage_start_at = $1, modified_at = CURRENT_TIMESTAMP
WHERE metric IN ('route_usage', 'endpoint_attempt_classification')
  AND coverage_start_at IS NULL
  AND deleted_at IS NULL
"""

UPSERT_GATEWAY_HOURLY_SQL: Final[str] = """
INSERT INTO gateway_usage_hourly (
    id, account_id, app_id, gateway_id, chain, network, bucket_hour,
    total_requests, successful_requests, failed_requests, total_duration_ms,
    total_request_bytes, total_response_bytes, cache_eligible_requests, cache_hit_requests,
    created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::timestamptz[],
    $8::bigint[], $9::bigint[], $10::bigint[], $11::bigint[],
    $12::bigint[], $13::bigint[], $14::bigint[], $15::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, chain, network, bucket_hour) DO UPDATE SET
    total_requests = gateway_usage_hourly.total_requests + EXCLUDED.total_requests,
    successful_requests = gateway_usage_hourly.successful_requests + EXCLUDED.successful_requests,
    failed_requests = gateway_usage_hourly.failed_requests + EXCLUDED.failed_requests,
    total_duration_ms = gateway_usage_hourly.total_duration_ms + EXCLUDED.total_duration_ms,
    total_request_bytes = gateway_usage_hourly.total_request_bytes + EXCLUDED.total_request_bytes,
    total_response_bytes = gateway_usage_hourly.total_response_bytes + EXCLUDED.total_response_bytes,
    cache_eligible_requests = gateway_usage_hourly.cache_eligible_requests + EXCLUDED.cache_eligible_requests,
    cache_hit_requests = gateway_usage_hourly.cache_hit_requests + EXCLUDED.cache_hit_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_METHOD_HOURLY_SQL: Final[str] = """
INSERT INTO gateway_usage_method_hourly (
    id, account_id, app_id, gateway_id, chain, network, method, bucket_hour,
    total_requests, successful_requests, failed_requests, total_duration_ms,
    total_request_bytes, total_response_bytes, cache_eligible_requests, cache_hit_requests,
    created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::timestamptz[],
    $9::bigint[], $10::bigint[], $11::bigint[], $12::bigint[],
    $13::bigint[], $14::bigint[], $15::bigint[], $16::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, chain, network, method, bucket_hour) DO UPDATE SET
    total_requests = gateway_usage_method_hourly.total_requests + EXCLUDED.total_requests,
    successful_requests = gateway_usage_method_hourly.successful_requests + EXCLUDED.successful_requests,
    failed_requests = gateway_usage_method_hourly.failed_requests + EXCLUDED.failed_requests,
    total_duration_ms = gateway_usage_method_hourly.total_duration_ms + EXCLUDED.total_duration_ms,
    total_request_bytes = gateway_usage_method_hourly.total_request_bytes + EXCLUDED.total_request_bytes,
    total_response_bytes = gateway_usage_method_hourly.total_response_bytes + EXCLUDED.total_response_bytes,
    cache_eligible_requests = gateway_usage_method_hourly.cache_eligible_requests + EXCLUDED.cache_eligible_requests,
    cache_hit_requests = gateway_usage_method_hourly.cache_hit_requests + EXCLUDED.cache_hit_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_GATEWAY_FINE_SQL: Final[str] = """
INSERT INTO gateway_usage_five_minute (
    id, account_id, app_id, gateway_id, chain, network, bucket_start,
    total_requests, successful_requests, failed_requests, total_duration_ms,
    total_request_bytes, total_response_bytes, cache_eligible_requests, cache_hit_requests,
    created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::timestamptz[],
    $8::bigint[], $9::bigint[], $10::bigint[], $11::bigint[],
    $12::bigint[], $13::bigint[], $14::bigint[], $15::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, chain, network, bucket_start) DO UPDATE SET
    total_requests = gateway_usage_five_minute.total_requests + EXCLUDED.total_requests,
    successful_requests = gateway_usage_five_minute.successful_requests + EXCLUDED.successful_requests,
    failed_requests = gateway_usage_five_minute.failed_requests + EXCLUDED.failed_requests,
    total_duration_ms = gateway_usage_five_minute.total_duration_ms + EXCLUDED.total_duration_ms,
    total_request_bytes = gateway_usage_five_minute.total_request_bytes + EXCLUDED.total_request_bytes,
    total_response_bytes = gateway_usage_five_minute.total_response_bytes + EXCLUDED.total_response_bytes,
    cache_eligible_requests = gateway_usage_five_minute.cache_eligible_requests + EXCLUDED.cache_eligible_requests,
    cache_hit_requests = gateway_usage_five_minute.cache_hit_requests + EXCLUDED.cache_hit_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_METHOD_FINE_SQL: Final[str] = """
INSERT INTO gateway_usage_method_five_minute (
    id, account_id, app_id, gateway_id, chain, network, method, bucket_start,
    total_requests, successful_requests, failed_requests, total_duration_ms,
    total_request_bytes, total_response_bytes, cache_eligible_requests, cache_hit_requests,
    created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::timestamptz[],
    $9::bigint[], $10::bigint[], $11::bigint[], $12::bigint[],
    $13::bigint[], $14::bigint[], $15::bigint[], $16::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, chain, network, method, bucket_start) DO UPDATE SET
    total_requests = gateway_usage_method_five_minute.total_requests + EXCLUDED.total_requests,
    successful_requests = gateway_usage_method_five_minute.successful_requests + EXCLUDED.successful_requests,
    failed_requests = gateway_usage_method_five_minute.failed_requests + EXCLUDED.failed_requests,
    total_duration_ms = gateway_usage_method_five_minute.total_duration_ms + EXCLUDED.total_duration_ms,
    total_request_bytes = gateway_usage_method_five_minute.total_request_bytes + EXCLUDED.total_request_bytes,
    total_response_bytes = gateway_usage_method_five_minute.total_response_bytes + EXCLUDED.total_response_bytes,
    cache_eligible_requests = gateway_usage_method_five_minute.cache_eligible_requests + EXCLUDED.cache_eligible_requests,
    cache_hit_requests = gateway_usage_method_five_minute.cache_hit_requests + EXCLUDED.cache_hit_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_ENDPOINT_HOURLY_SQL: Final[str] = """
INSERT INTO gateway_usage_endpoint_hourly (
    id, account_id, app_id, gateway_id, route_id, endpoint_id, chain, network, bucket_hour,
    total_attempts, first_attempts, retry_attempts, created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::text[],
    $9::timestamptz[], $10::bigint[], $11::bigint[], $12::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, route_id, endpoint_id, chain, network, bucket_hour) DO UPDATE SET
    total_attempts = gateway_usage_endpoint_hourly.total_attempts + EXCLUDED.total_attempts,
    first_attempts = COALESCE(gateway_usage_endpoint_hourly.first_attempts, 0) + EXCLUDED.first_attempts,
    retry_attempts = COALESCE(gateway_usage_endpoint_hourly.retry_attempts, 0) + EXCLUDED.retry_attempts,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_ENDPOINT_FINE_SQL: Final[str] = """
INSERT INTO gateway_usage_endpoint_five_minute (
    id, account_id, app_id, gateway_id, route_id, endpoint_id, chain, network, bucket_start,
    total_attempts, first_attempts, retry_attempts, created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::text[],
    $9::timestamptz[], $10::bigint[], $11::bigint[], $12::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, route_id, endpoint_id, chain, network, bucket_start) DO UPDATE SET
    total_attempts = gateway_usage_endpoint_five_minute.total_attempts + EXCLUDED.total_attempts,
    first_attempts = COALESCE(gateway_usage_endpoint_five_minute.first_attempts, 0) + EXCLUDED.first_attempts,
    retry_attempts = COALESCE(gateway_usage_endpoint_five_minute.retry_attempts, 0) + EXCLUDED.retry_attempts,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_ROUTE_HOURLY_SQL: Final[str] = """
INSERT INTO gateway_usage_route_hourly (
    id, account_id, app_id, gateway_id, route_id, chain, network, bucket_hour,
    routed_requests, successful_requests, failed_requests, total_duration_ms, total_attempts,
    multi_attempt_requests, exhausted_requests, created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::timestamptz[],
    $9::bigint[], $10::bigint[], $11::bigint[], $12::bigint[], $13::bigint[], $14::bigint[], $15::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, route_id, chain, network, bucket_hour) DO UPDATE SET
    routed_requests = gateway_usage_route_hourly.routed_requests + EXCLUDED.routed_requests,
    successful_requests = gateway_usage_route_hourly.successful_requests + EXCLUDED.successful_requests,
    failed_requests = gateway_usage_route_hourly.failed_requests + EXCLUDED.failed_requests,
    total_duration_ms = gateway_usage_route_hourly.total_duration_ms + EXCLUDED.total_duration_ms,
    total_attempts = gateway_usage_route_hourly.total_attempts + EXCLUDED.total_attempts,
    multi_attempt_requests = gateway_usage_route_hourly.multi_attempt_requests + EXCLUDED.multi_attempt_requests,
    exhausted_requests = gateway_usage_route_hourly.exhausted_requests + EXCLUDED.exhausted_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

UPSERT_ROUTE_FINE_SQL: Final[str] = """
INSERT INTO gateway_usage_route_five_minute (
    id, account_id, app_id, gateway_id, route_id, chain, network, bucket_start,
    routed_requests, successful_requests, failed_requests, total_duration_ms, total_attempts,
    multi_attempt_requests, exhausted_requests, created_at, modified_at
)
SELECT *, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM UNNEST(
    $1::text[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::timestamptz[],
    $9::bigint[], $10::bigint[], $11::bigint[], $12::bigint[], $13::bigint[], $14::bigint[], $15::bigint[]
)
ON CONFLICT (account_id, app_id, gateway_id, route_id, chain, network, bucket_start) DO UPDATE SET
    routed_requests = gateway_usage_route_five_minute.routed_requests + EXCLUDED.routed_requests,
    successful_requests = gateway_usage_route_five_minute.successful_requests + EXCLUDED.successful_requests,
    failed_requests = gateway_usage_route_five_minute.failed_requests + EXCLUDED.failed_requests,
    total_duration_ms = gateway_usage_route_five_minute.total_duration_ms + EXCLUDED.total_duration_ms,
    total_attempts = gateway_usage_route_five_minute.total_attempts + EXCLUDED.total_attempts,
    multi_attempt_requests = gateway_usage_route_five_minute.multi_attempt_requests + EXCLUDED.multi_attempt_requests,
    exhausted_requests = gateway_usage_route_five_minute.exhausted_requests + EXCLUDED.exhausted_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

MARK_ROLLUP_HOURS_SQL: Final[str] = """
INSERT INTO gateway_usage_rollup_hour (id, bucket_hour, created_at, modified_at)
SELECT * FROM UNNEST($1::text[], $2::timestamptz[], $3::timestamptz[], $4::timestamptz[])
ON CONFLICT (bucket_hour) DO UPDATE SET modified_at = EXCLUDED.modified_at, deleted_at = NULL
"""

ROLLUP_GATEWAY_HOUR_SQL: Final[str] = """
INSERT INTO gateway_usage_hourly (
    id, account_id, app_id, gateway_id, chain, network, bucket_hour,
    total_requests, successful_requests, failed_requests, total_duration_ms,
    total_request_bytes, total_response_bytes, cache_eligible_requests, cache_hit_requests,
    created_at, modified_at
)
SELECT
    LEFT(REPLACE(gen_random_uuid()::text, '-', ''), 21), account_id, app_id, gateway_id, chain, network, $1,
    SUM(total_requests), SUM(successful_requests), SUM(failed_requests), SUM(total_duration_ms),
    SUM(total_request_bytes), SUM(total_response_bytes), SUM(cache_eligible_requests), SUM(cache_hit_requests),
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM gateway_usage_five_minute
WHERE bucket_start >= $1 AND bucket_start < $1 + INTERVAL '1 hour' AND deleted_at IS NULL
GROUP BY account_id, app_id, gateway_id, chain, network
ON CONFLICT (account_id, app_id, gateway_id, chain, network, bucket_hour) DO UPDATE SET
    total_requests = EXCLUDED.total_requests,
    successful_requests = EXCLUDED.successful_requests,
    failed_requests = EXCLUDED.failed_requests,
    total_duration_ms = EXCLUDED.total_duration_ms,
    total_request_bytes = EXCLUDED.total_request_bytes,
    total_response_bytes = EXCLUDED.total_response_bytes,
    cache_eligible_requests = EXCLUDED.cache_eligible_requests,
    cache_hit_requests = EXCLUDED.cache_hit_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

ROLLUP_METHOD_HOUR_SQL: Final[str] = """
INSERT INTO gateway_usage_method_hourly (
    id, account_id, app_id, gateway_id, chain, network, method, bucket_hour,
    total_requests, successful_requests, failed_requests, total_duration_ms,
    total_request_bytes, total_response_bytes, cache_eligible_requests, cache_hit_requests,
    created_at, modified_at
)
SELECT
    LEFT(REPLACE(gen_random_uuid()::text, '-', ''), 21), account_id, app_id, gateway_id, chain, network, method, $1,
    SUM(total_requests), SUM(successful_requests), SUM(failed_requests), SUM(total_duration_ms),
    SUM(total_request_bytes), SUM(total_response_bytes), SUM(cache_eligible_requests), SUM(cache_hit_requests),
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM gateway_usage_method_five_minute
WHERE bucket_start >= $1 AND bucket_start < $1 + INTERVAL '1 hour' AND deleted_at IS NULL
GROUP BY account_id, app_id, gateway_id, chain, network, method
ON CONFLICT (account_id, app_id, gateway_id, chain, network, method, bucket_hour) DO UPDATE SET
    total_requests = EXCLUDED.total_requests,
    successful_requests = EXCLUDED.successful_requests,
    failed_requests = EXCLUDED.failed_requests,
    total_duration_ms = EXCLUDED.total_duration_ms,
    total_request_bytes = EXCLUDED.total_request_bytes,
    total_response_bytes = EXCLUDED.total_response_bytes,
    cache_eligible_requests = EXCLUDED.cache_eligible_requests,
    cache_hit_requests = EXCLUDED.cache_hit_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

ROLLUP_ENDPOINT_HOUR_SQL: Final[str] = """
INSERT INTO gateway_usage_endpoint_hourly (
    id, account_id, app_id, gateway_id, route_id, endpoint_id, chain, network, bucket_hour,
    total_attempts, first_attempts, retry_attempts, created_at, modified_at
)
SELECT
    LEFT(REPLACE(gen_random_uuid()::text, '-', ''), 21), account_id, app_id, gateway_id, route_id, endpoint_id,
    chain, network, $1, SUM(total_attempts), COALESCE(SUM(first_attempts), 0), COALESCE(SUM(retry_attempts), 0),
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM gateway_usage_endpoint_five_minute
WHERE bucket_start >= $1 AND bucket_start < $1 + INTERVAL '1 hour' AND deleted_at IS NULL
GROUP BY account_id, app_id, gateway_id, route_id, endpoint_id, chain, network
ON CONFLICT (account_id, app_id, gateway_id, route_id, endpoint_id, chain, network, bucket_hour) DO UPDATE SET
    total_attempts = EXCLUDED.total_attempts,
    first_attempts = EXCLUDED.first_attempts,
    retry_attempts = EXCLUDED.retry_attempts,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

ROLLUP_ROUTE_HOUR_SQL: Final[str] = """
INSERT INTO gateway_usage_route_hourly (
    id, account_id, app_id, gateway_id, route_id, chain, network, bucket_hour,
    routed_requests, successful_requests, failed_requests, total_duration_ms, total_attempts,
    multi_attempt_requests, exhausted_requests, created_at, modified_at
)
SELECT
    LEFT(REPLACE(gen_random_uuid()::text, '-', ''), 21), account_id, app_id, gateway_id, route_id, chain, network, $1,
    SUM(routed_requests), SUM(successful_requests), SUM(failed_requests), SUM(total_duration_ms), SUM(total_attempts),
    SUM(multi_attempt_requests), SUM(exhausted_requests), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM gateway_usage_route_five_minute
WHERE bucket_start >= $1 AND bucket_start < $1 + INTERVAL '1 hour' AND deleted_at IS NULL
GROUP BY account_id, app_id, gateway_id, route_id, chain, network
ON CONFLICT (account_id, app_id, gateway_id, route_id, chain, network, bucket_hour) DO UPDATE SET
    routed_requests = EXCLUDED.routed_requests,
    successful_requests = EXCLUDED.successful_requests,
    failed_requests = EXCLUDED.failed_requests,
    total_duration_ms = EXCLUDED.total_duration_ms,
    total_attempts = EXCLUDED.total_attempts,
    multi_attempt_requests = EXCLUDED.multi_attempt_requests,
    exhausted_requests = EXCLUDED.exhausted_requests,
    modified_at = CURRENT_TIMESTAMP,
    deleted_at = NULL
"""

MAINTAIN_PARTITIONS_SQL: Final[str] = """
SELECT created_partitions, dropped_partitions
FROM gateway_usage_maintain_partitions($1, $2)
"""

HAS_PARTITION_MAINTENANCE_SQL: Final[str] = """
SELECT to_regprocedure('gateway_usage_maintain_partitions(timestamp with time zone,integer)') IS NOT NULL AS available
"""

MAINTAIN_FINE_PARTITIONS_SQL: Final[str] = """
SELECT created_partitions, dropped_partitions
FROM gateway_usage_fine_maintain_partitions($1, $2)
"""

HAS_FINE_PARTITION_MAINTENANCE_SQL: Final[str] = """
SELECT to_regprocedure('gateway_usage_fine_maintain_partitions(timestamp with time zone,integer)') IS NOT NULL AS available
"""

DELETE_GATEWAY_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_hourly
    WHERE bucket_hour < date_trunc('month', $1::timestamptz) - make_interval(months => $2::integer - 1)
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_METHOD_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_method_hourly
    WHERE bucket_hour < date_trunc('month', $1::timestamptz) - make_interval(months => $2::integer - 1)
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_ENDPOINT_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_endpoint_hourly
    WHERE bucket_hour < date_trunc('month', $1::timestamptz) - make_interval(months => $2::integer - 1)
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_ROUTE_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_route_hourly
    WHERE bucket_hour < date_trunc('month', $1::timestamptz) - make_interval(months => $2::integer - 1)
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_GATEWAY_FINE_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_five_minute AS usage
    WHERE usage.bucket_start < $1::timestamptz - make_interval(hours => $2::integer)
      AND NOT EXISTS (
          SELECT 1 FROM gateway_usage_rollup_hour AS dirty
          WHERE dirty.bucket_hour = date_trunc('hour', usage.bucket_start) AND dirty.deleted_at IS NULL
      )
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_METHOD_FINE_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_method_five_minute AS usage
    WHERE usage.bucket_start < $1::timestamptz - make_interval(hours => $2::integer)
      AND NOT EXISTS (
          SELECT 1 FROM gateway_usage_rollup_hour AS dirty
          WHERE dirty.bucket_hour = date_trunc('hour', usage.bucket_start) AND dirty.deleted_at IS NULL
      )
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_ENDPOINT_FINE_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_endpoint_five_minute AS usage
    WHERE usage.bucket_start < $1::timestamptz - make_interval(hours => $2::integer)
      AND NOT EXISTS (
          SELECT 1 FROM gateway_usage_rollup_hour AS dirty
          WHERE dirty.bucket_hour = date_trunc('hour', usage.bucket_start) AND dirty.deleted_at IS NULL
      )
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""

DELETE_ROUTE_FINE_RETENTION_SQL: Final[str] = """
WITH deleted AS (
    DELETE FROM gateway_usage_route_five_minute AS usage
    WHERE usage.bucket_start < $1::timestamptz - make_interval(hours => $2::integer)
      AND NOT EXISTS (
          SELECT 1 FROM gateway_usage_rollup_hour AS dirty
          WHERE dirty.bucket_hour = date_trunc('hour', usage.bucket_start) AND dirty.deleted_at IS NULL
      )
    RETURNING 1
)
SELECT COUNT(*)::bigint AS deleted_rows FROM deleted
"""


@dataclass(slots=True, kw_only=True)
class UsageAggregate:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_ms: int = 0
    total_request_bytes: int = 0
    total_response_bytes: int = 0
    cache_eligible_requests: int = 0
    cache_hit_requests: int = 0


@dataclass(slots=True, kw_only=True)
class EndpointUsageAggregate:
    total_attempts: int = 0
    first_attempts: int = 0
    retry_attempts: int = 0


@dataclass(slots=True, kw_only=True)
class RouteUsageAggregate:
    routed_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_ms: int = 0
    total_attempts: int = 0
    multi_attempt_requests: int = 0
    exhausted_requests: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class UsagePartitionResult:
    created_partitions: int
    dropped_partitions: int
    deleted_gateway_rows: int = 0
    deleted_method_rows: int = 0
    deleted_endpoint_rows: int = 0
    deleted_route_rows: int = 0
    deleted_fine_gateway_rows: int = 0
    deleted_fine_method_rows: int = 0
    deleted_fine_endpoint_rows: int = 0
    deleted_fine_route_rows: int = 0


class GatewayUsageStore:
    @staticmethod
    async def lock_checkpoint(connection: BaseDBAsyncClient) -> GatewayUsageCheckpoint:
        await connection.execute_query(
            """
            INSERT INTO gateway_usage_checkpoint (id, created_at, modified_at, last_stream_id)
            VALUES ('usage-v3-checkpoint', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '0-0')
            ON CONFLICT (id) DO NOTHING
            """
        )
        checkpoint = await (
            GatewayUsageCheckpoint.filter(id='usage-v3-checkpoint', deleted_at=None)
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if checkpoint is None:
            raise RuntimeError('Gateway Usage checkpoint is missing.')
        return checkpoint

    @staticmethod
    async def activate_route_aware_metrics(connection: BaseDBAsyncClient, coverage_start_at: datetime) -> None:
        await connection.execute_query(ACTIVATE_ROUTE_AWARE_METRICS_SQL, [coverage_start_at])

    @staticmethod
    async def get_known_methods(
        connection: BaseDBAsyncClient,
        scopes: set[UsageScope],
        *,
        excluded_method: str,
    ) -> dict[UsageScope, set[str]]:
        scope_filter = Q()
        for scope in scopes:
            scope_filter |= Q(
                account_id=scope[0],
                app_id=scope[1],
                gateway_id=scope[2],
                chain=scope[3],
                network=scope[4],
                bucket_hour=scope[5],
            )
        hourly_rows = await (
            GatewayUsageMethodHourly.filter(scope_filter, deleted_at=None)
            .exclude(method=excluded_method)
            .using_db(connection)
            .values('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'bucket_hour', 'method')
        )
        fine_filter = Q()
        for scope in scopes:
            fine_filter |= Q(
                account_id=scope[0],
                app_id=scope[1],
                gateway_id=scope[2],
                chain=scope[3],
                network=scope[4],
                bucket_start__gte=scope[5],
                bucket_start__lt=scope[5] + timedelta(hours=1),
            )
        fine_rows = await (
            GatewayUsageMethodFiveMinute.filter(fine_filter, deleted_at=None)
            .exclude(method=excluded_method)
            .using_db(connection)
            .values('account_id', 'app_id', 'gateway_id', 'chain', 'network', 'bucket_start', 'method')
        )
        known: dict[UsageScope, set[str]] = {scope: set() for scope in scopes}
        for row in hourly_rows:
            bucket_hour = row['bucket_hour']
            if not isinstance(bucket_hour, datetime):
                raise RuntimeError('Gateway Usage method bucket is invalid.')
            scope = (
                str(row['account_id']),
                str(row['app_id']),
                str(row['gateway_id']),
                str(row['chain']),
                str(row['network']),
                bucket_hour,
            )
            known.setdefault(scope, set()).add(str(row['method']))
        for row in fine_rows:
            bucket_start = row['bucket_start']
            if not isinstance(bucket_start, datetime):
                raise RuntimeError('Gateway Usage method bucket is invalid.')
            bucket_hour = bucket_start.replace(minute=0, second=0, microsecond=0)
            scope = (
                str(row['account_id']),
                str(row['app_id']),
                str(row['gateway_id']),
                str(row['chain']),
                str(row['network']),
                bucket_hour,
            )
            known.setdefault(scope, set()).add(str(row['method']))
        return known

    @staticmethod
    async def upsert_gateway_fine(
        connection: BaseDBAsyncClient,
        rows: dict[UsageFineScope, UsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        values: list[Any] = GatewayUsageStore._scope_arrays(ordered)
        values.extend(GatewayUsageStore._metric_arrays(ordered))
        await connection.execute_query(UPSERT_GATEWAY_FINE_SQL, values)

    @staticmethod
    async def upsert_method_fine(
        connection: BaseDBAsyncClient,
        rows: dict[UsageFineMethodKey, UsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        keys = [item[0] for item in ordered]
        values: list[Any] = [
            [NANOIDField.nanoid() for _key in keys],
            [key[0] for key in keys],
            [key[1] for key in keys],
            [key[2] for key in keys],
            [key[3] for key in keys],
            [key[4] for key in keys],
            [key[5] for key in keys],
            [key[6] for key in keys],
        ]
        values.extend(GatewayUsageStore._metric_arrays(ordered))
        await connection.execute_query(UPSERT_METHOD_FINE_SQL, values)

    @staticmethod
    async def upsert_endpoint_fine(
        connection: BaseDBAsyncClient,
        rows: dict[UsageEndpointKey, EndpointUsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        values = GatewayUsageStore._endpoint_arrays(ordered)
        await connection.execute_query(UPSERT_ENDPOINT_FINE_SQL, values)

    @staticmethod
    async def upsert_route_fine(
        connection: BaseDBAsyncClient,
        rows: dict[UsageRouteKey, RouteUsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        values = GatewayUsageStore._route_arrays(ordered)
        await connection.execute_query(UPSERT_ROUTE_FINE_SQL, values)

    @staticmethod
    async def mark_rollup_hours(connection: BaseDBAsyncClient, hours: set[datetime]) -> None:
        ordered = sorted(hours)
        if not ordered:
            return
        modified_at = datetime.now(UTC)
        values = [
            [NANOIDField.nanoid() for _hour in ordered],
            ordered,
            [modified_at for _hour in ordered],
            [modified_at for _hour in ordered],
        ]
        await connection.execute_query(MARK_ROLLUP_HOURS_SQL, values)

    @staticmethod
    async def get_rollup_hours(connection: BaseDBAsyncClient, *, limit: int) -> list[datetime]:
        rows = await connection.execute_query_dict(
            """
            SELECT bucket_hour
            FROM gateway_usage_rollup_hour
            WHERE deleted_at IS NULL
            ORDER BY bucket_hour
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            [limit],
        )
        hours: list[datetime] = []
        for row in rows:
            bucket_hour = row.get('bucket_hour')
            if not isinstance(bucket_hour, datetime):
                raise RuntimeError('Gateway Usage rollup hour is invalid.')
            hours.append(bucket_hour)
        return hours

    @staticmethod
    async def rollup_hour(connection: BaseDBAsyncClient, bucket_hour: datetime) -> None:
        await connection.execute_query(ROLLUP_GATEWAY_HOUR_SQL, [bucket_hour])
        await connection.execute_query(ROLLUP_METHOD_HOUR_SQL, [bucket_hour])
        await connection.execute_query(ROLLUP_ENDPOINT_HOUR_SQL, [bucket_hour])
        await connection.execute_query(ROLLUP_ROUTE_HOUR_SQL, [bucket_hour])
        await connection.execute_query('DELETE FROM gateway_usage_rollup_hour WHERE bucket_hour = $1', [bucket_hour])

    @staticmethod
    async def upsert_gateway_hourly(
        connection: BaseDBAsyncClient,
        rows: dict[UsageScope, UsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        values: list[Any] = GatewayUsageStore._scope_arrays(ordered)
        values.extend(GatewayUsageStore._metric_arrays(ordered))
        await connection.execute_query(UPSERT_GATEWAY_HOURLY_SQL, values)

    @staticmethod
    async def upsert_method_hourly(
        connection: BaseDBAsyncClient,
        rows: dict[tuple[str, str, str, str, str, str, datetime], UsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        keys = [item[0] for item in ordered]
        values: list[Any] = [
            [NANOIDField.nanoid() for _key in keys],
            [key[0] for key in keys],
            [key[1] for key in keys],
            [key[2] for key in keys],
            [key[3] for key in keys],
            [key[4] for key in keys],
            [key[5] for key in keys],
            [key[6] for key in keys],
        ]
        values.extend(GatewayUsageStore._metric_arrays(ordered))
        await connection.execute_query(UPSERT_METHOD_HOURLY_SQL, values)

    @staticmethod
    async def upsert_endpoint_hourly(
        connection: BaseDBAsyncClient,
        rows: dict[UsageEndpointKey, EndpointUsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        values = GatewayUsageStore._endpoint_arrays(ordered)
        await connection.execute_query(UPSERT_ENDPOINT_HOURLY_SQL, values)

    @staticmethod
    async def upsert_route_hourly(
        connection: BaseDBAsyncClient,
        rows: dict[UsageRouteKey, RouteUsageAggregate],
    ) -> None:
        if not rows:
            return
        ordered = sorted(rows.items())
        values = GatewayUsageStore._route_arrays(ordered)
        await connection.execute_query(UPSERT_ROUTE_HOURLY_SQL, values)

    @staticmethod
    async def update_checkpoint(
        connection: BaseDBAsyncClient,
        checkpoint: GatewayUsageCheckpoint,
        stream_id: str,
    ) -> None:
        checkpoint.last_stream_id = stream_id
        await checkpoint.save(using_db=connection, update_fields=('last_stream_id', 'modified_at'))

    @staticmethod
    async def maintain_partitions(reference_at: datetime) -> UsagePartitionResult:
        connection = connections.get('default')
        availability = await connection.execute_query_dict(HAS_PARTITION_MAINTENANCE_SQL)
        created_partitions = 0
        dropped_partitions = 0
        if availability and availability[0].get('available') is True:
            rows = await connection.execute_query_dict(
                MAINTAIN_PARTITIONS_SQL,
                [reference_at, CONF.USAGE_HOURLY_RETENTION_MONTHS],
            )
            if not rows:
                raise RuntimeError('Gateway Usage partition maintenance returned no result.')
            created_partitions += int(rows[0]['created_partitions'])
            dropped_partitions += int(rows[0]['dropped_partitions'])
        fine_availability = await connection.execute_query_dict(HAS_FINE_PARTITION_MAINTENANCE_SQL)
        if fine_availability and fine_availability[0].get('available') is True:
            fine_rows = await connection.execute_query_dict(
                MAINTAIN_FINE_PARTITIONS_SQL,
                [reference_at, CONF.USAGE_FINE_RETENTION_HOURS],
            )
            if not fine_rows:
                raise RuntimeError('Gateway Usage fine partition maintenance returned no result.')
            created_partitions += int(fine_rows[0]['created_partitions'])
            dropped_partitions += int(fine_rows[0]['dropped_partitions'])

        async with in_tx() as transaction:
            gateway_rows = await transaction.execute_query_dict(
                DELETE_GATEWAY_RETENTION_SQL,
                [reference_at, CONF.USAGE_HOURLY_RETENTION_MONTHS],
            )
            method_rows = await transaction.execute_query_dict(
                DELETE_METHOD_RETENTION_SQL,
                [reference_at, CONF.USAGE_HOURLY_RETENTION_MONTHS],
            )
            endpoint_rows = await transaction.execute_query_dict(
                DELETE_ENDPOINT_RETENTION_SQL,
                [reference_at, CONF.USAGE_HOURLY_RETENTION_MONTHS],
            )
            route_rows = await transaction.execute_query_dict(
                DELETE_ROUTE_RETENTION_SQL,
                [reference_at, CONF.USAGE_HOURLY_RETENTION_MONTHS],
            )
            fine_gateway_rows = await transaction.execute_query_dict(
                DELETE_GATEWAY_FINE_RETENTION_SQL,
                [reference_at, CONF.USAGE_FINE_RETENTION_HOURS],
            )
            fine_method_rows = await transaction.execute_query_dict(
                DELETE_METHOD_FINE_RETENTION_SQL,
                [reference_at, CONF.USAGE_FINE_RETENTION_HOURS],
            )
            fine_endpoint_rows = await transaction.execute_query_dict(
                DELETE_ENDPOINT_FINE_RETENTION_SQL,
                [reference_at, CONF.USAGE_FINE_RETENTION_HOURS],
            )
            fine_route_rows = await transaction.execute_query_dict(
                DELETE_ROUTE_FINE_RETENTION_SQL,
                [reference_at, CONF.USAGE_FINE_RETENTION_HOURS],
            )
        if (
            not gateway_rows
            or not method_rows
            or not endpoint_rows
            or not route_rows
            or not fine_gateway_rows
            or not fine_method_rows
            or not fine_endpoint_rows
            or not fine_route_rows
        ):
            raise RuntimeError('Gateway Usage row retention returned no result.')
        return UsagePartitionResult(
            created_partitions=created_partitions,
            dropped_partitions=dropped_partitions,
            deleted_gateway_rows=int(gateway_rows[0]['deleted_rows']),
            deleted_method_rows=int(method_rows[0]['deleted_rows']),
            deleted_endpoint_rows=int(endpoint_rows[0]['deleted_rows']),
            deleted_route_rows=int(route_rows[0]['deleted_rows']),
            deleted_fine_gateway_rows=int(fine_gateway_rows[0]['deleted_rows']),
            deleted_fine_method_rows=int(fine_method_rows[0]['deleted_rows']),
            deleted_fine_endpoint_rows=int(fine_endpoint_rows[0]['deleted_rows']),
            deleted_fine_route_rows=int(fine_route_rows[0]['deleted_rows']),
        )

    @staticmethod
    def _scope_arrays(rows: list[tuple[UsageScope, UsageAggregate]]) -> list[Any]:
        keys = [item[0] for item in rows]
        return [
            [NANOIDField.nanoid() for _key in keys],
            [key[0] for key in keys],
            [key[1] for key in keys],
            [key[2] for key in keys],
            [key[3] for key in keys],
            [key[4] for key in keys],
            [key[5] for key in keys],
        ]

    @staticmethod
    def _metric_arrays(rows: list[tuple[Any, UsageAggregate]]) -> list[Any]:
        metrics = [item[1] for item in rows]
        return [
            [metric.total_requests for metric in metrics],
            [metric.successful_requests for metric in metrics],
            [metric.failed_requests for metric in metrics],
            [metric.total_duration_ms for metric in metrics],
            [metric.total_request_bytes for metric in metrics],
            [metric.total_response_bytes for metric in metrics],
            [metric.cache_eligible_requests for metric in metrics],
            [metric.cache_hit_requests for metric in metrics],
        ]

    @staticmethod
    def _endpoint_arrays(rows: list[tuple[UsageEndpointKey, EndpointUsageAggregate]]) -> list[Any]:
        keys = [item[0] for item in rows]
        metrics = [item[1] for item in rows]
        return [
            [NANOIDField.nanoid() for _key in keys],
            [key[0] for key in keys],
            [key[1] for key in keys],
            [key[2] for key in keys],
            [key[3] for key in keys],
            [key[4] for key in keys],
            [key[5] for key in keys],
            [key[6] for key in keys],
            [key[7] for key in keys],
            [metric.total_attempts for metric in metrics],
            [metric.first_attempts for metric in metrics],
            [metric.retry_attempts for metric in metrics],
        ]

    @staticmethod
    def _route_arrays(rows: list[tuple[UsageRouteKey, RouteUsageAggregate]]) -> list[Any]:
        keys = [item[0] for item in rows]
        metrics = [item[1] for item in rows]
        return [
            [NANOIDField.nanoid() for _key in keys],
            [key[0] for key in keys],
            [key[1] for key in keys],
            [key[2] for key in keys],
            [key[3] for key in keys],
            [key[4] for key in keys],
            [key[5] for key in keys],
            [key[6] for key in keys],
            [metric.routed_requests for metric in metrics],
            [metric.successful_requests for metric in metrics],
            [metric.failed_requests for metric in metrics],
            [metric.total_duration_ms for metric in metrics],
            [metric.total_attempts for metric in metrics],
            [metric.multi_attempt_requests for metric in metrics],
            [metric.exhausted_requests for metric in metrics],
        ]
