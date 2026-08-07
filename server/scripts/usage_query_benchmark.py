import argparse
import asyncio
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import orjson

SAMPLES = 10
WARMUPS = 3
MAX_P95_RATIO = 1.1
PAYLOAD_BUDGETS = {'methods': 0.6, 'networks': 0.7, 'gateways': 0.25}

WIDE_FIELDS = """
    SUM(total_requests) AS total_requests,
    SUM(successful_requests) AS successful_requests,
    SUM(failed_requests) AS failed_requests,
    SUM(total_duration_ms) AS total_duration_ms,
    SUM(total_request_bytes) AS total_request_bytes,
    SUM(total_response_bytes) AS total_response_bytes,
    SUM(cache_eligible_requests) AS cache_eligible_requests,
    SUM(cache_hit_requests) AS cache_hit_requests
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    gateways: int
    methods: int
    hours: int = 24 * 30


PROFILES = {
    'quick': Profile(gateways=10, methods=20),
    'standard': Profile(gateways=20, methods=50),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryPair:
    wide: str
    narrow: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QuerySample:
    elapsed_ms: float
    buffer_blocks: int


QUERIES = {
    'methods': QueryPair(
        wide=f"""
            SELECT method, date_trunc('day', bucket_hour) AS bucket_start, {WIDE_FIELDS}
            FROM gateway_usage_method_hourly
            WHERE account_id = 'benchmark-account' AND bucket_hour >= $1
            GROUP BY method, bucket_start
            ORDER BY method, bucket_start
        """,
        narrow="""
            SELECT method, date_trunc('day', bucket_hour) AS bucket_start,
                   SUM(total_requests) AS total_requests,
                   SUM(cache_eligible_requests) AS cache_eligible_requests,
                   SUM(cache_hit_requests) AS cache_hit_requests
            FROM gateway_usage_method_hourly
            WHERE account_id = 'benchmark-account' AND bucket_hour >= $1
            GROUP BY method, bucket_start
            ORDER BY method, bucket_start
        """,
    ),
    'networks': QueryPair(
        wide=f"""
            SELECT chain, network, date_trunc('day', bucket_hour) AS bucket_start, {WIDE_FIELDS}
            FROM gateway_usage_hourly
            WHERE account_id = 'benchmark-account' AND bucket_hour >= $1
            GROUP BY chain, network, bucket_start
            ORDER BY chain, network, bucket_start
        """,
        narrow="""
            SELECT chain, network, date_trunc('day', bucket_hour) AS bucket_start,
                   SUM(total_requests) AS total_requests,
                   SUM(total_duration_ms) AS total_duration_ms,
                   SUM(cache_eligible_requests) AS cache_eligible_requests,
                   SUM(cache_hit_requests) AS cache_hit_requests
            FROM gateway_usage_hourly
            WHERE account_id = 'benchmark-account' AND bucket_hour >= $1
            GROUP BY chain, network, bucket_start
            ORDER BY chain, network, bucket_start
        """,
    ),
    'gateways': QueryPair(
        wide=f"""
            SELECT gateway_id, {WIDE_FIELDS}
            FROM gateway_usage_hourly
            WHERE account_id = 'benchmark-account' AND bucket_hour >= $1
            GROUP BY gateway_id
            ORDER BY total_requests DESC, gateway_id
            LIMIT 10
        """,
        narrow="""
            SELECT gateway_id, SUM(total_requests) AS total_requests
            FROM gateway_usage_hourly
            WHERE account_id = 'benchmark-account' AND bucket_hour >= $1
            GROUP BY gateway_id
            ORDER BY total_requests DESC, gateway_id
            LIMIT 10
        """,
    ),
}


def _test_postgres_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise argparse.ArgumentTypeError('PostgreSQL URL must use postgres:// or postgresql://.')
    if 'test' not in parsed.path.casefold():
        raise argparse.ArgumentTypeError('Refusing to benchmark a database whose name does not contain test.')
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Compare wide and narrow Usage aggregate queries.')
    parser.add_argument('--postgres-url', required=True, type=_test_postgres_url)
    parser.add_argument('--profile', choices=tuple(PROFILES), default='quick')
    return parser.parse_args()


async def _prepare_tables(connection: asyncpg.Connection, profile: Profile, end_at: datetime) -> None:
    await connection.execute(
        """
        CREATE TEMP TABLE gateway_usage_hourly (
            account_id TEXT NOT NULL,
            app_id TEXT NOT NULL,
            gateway_id TEXT NOT NULL,
            chain TEXT NOT NULL,
            network TEXT NOT NULL,
            bucket_hour TIMESTAMPTZ NOT NULL,
            total_requests BIGINT NOT NULL,
            successful_requests BIGINT NOT NULL,
            failed_requests BIGINT NOT NULL,
            total_duration_ms BIGINT NOT NULL,
            total_request_bytes BIGINT NOT NULL,
            total_response_bytes BIGINT NOT NULL,
            cache_eligible_requests BIGINT NOT NULL,
            cache_hit_requests BIGINT NOT NULL
        );
        CREATE TEMP TABLE gateway_usage_method_hourly (
            LIKE gateway_usage_hourly INCLUDING ALL,
            method TEXT NOT NULL
        );
        """
    )
    await connection.execute(
        """
        INSERT INTO gateway_usage_hourly
        SELECT 'benchmark-account', 'app-' || ((gateway_number - 1) % 5 + 1), 'gateway-' || gateway_number,
               CASE gateway_number % 4 WHEN 0 THEN 'ethereum' WHEN 1 THEN 'polygon' WHEN 2 THEN 'base' ELSE 'arbitrum' END,
               'mainnet', $1::timestamptz - hour_number * INTERVAL '1 hour', 100, 95, 5, 1200, 4000, 12000, 60, 45
        FROM generate_series(1, $2) AS gateway_number
        CROSS JOIN generate_series(1, $3) AS hour_number
        """,
        end_at,
        profile.gateways,
        profile.hours,
    )
    await connection.execute(
        """
        INSERT INTO gateway_usage_method_hourly
        SELECT gateway.*, 'method-' || method_number
        FROM gateway_usage_hourly AS gateway
        CROSS JOIN generate_series(1, $1) AS method_number
        """,
        profile.methods,
    )
    await connection.execute(
        'CREATE INDEX ON gateway_usage_hourly (account_id, bucket_hour); '
        'CREATE INDEX ON gateway_usage_method_hourly (account_id, bucket_hour); '
        'ANALYZE gateway_usage_hourly; ANALYZE gateway_usage_method_hourly;'
    )


def _plan_payload(value: object) -> dict[str, Any]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError('PostgreSQL returned an invalid EXPLAIN payload.')
    return {str(key): item for key, item in payload[0].items()}


async def _query_sample(connection: asyncpg.Connection, query: str, start_at: datetime) -> QuerySample:
    row = await connection.fetchrow(f'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}', start_at)
    if row is None:
        raise RuntimeError('PostgreSQL returned no EXPLAIN result.')
    payload = _plan_payload(row[0])
    plan = payload.get('Plan')
    if not isinstance(plan, dict):
        raise RuntimeError('PostgreSQL returned an invalid EXPLAIN plan.')
    buffer_blocks = sum(
        int(plan.get(field, 0))
        for field in ('Shared Hit Blocks', 'Shared Read Blocks', 'Local Hit Blocks', 'Local Read Blocks')
    )
    return QuerySample(elapsed_ms=float(payload['Execution Time']), buffer_blocks=buffer_blocks)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _json_rows(rows: list[asyncpg.Record]) -> list[dict[str, object]]:
    return [{key: int(value) if isinstance(value, Decimal) else value for key, value in row.items()} for row in rows]


async def _query_report(connection: asyncpg.Connection, pair: QueryPair, start_at: datetime) -> dict[str, float | int | bool]:
    for _ in range(WARMUPS):
        await _query_sample(connection, pair.wide, start_at)
        await _query_sample(connection, pair.narrow, start_at)
    wide_samples = [await _query_sample(connection, pair.wide, start_at) for _ in range(SAMPLES)]
    narrow_samples = [await _query_sample(connection, pair.narrow, start_at) for _ in range(SAMPLES)]
    wide_rows = _json_rows(await connection.fetch(pair.wide, start_at))
    narrow_rows = _json_rows(await connection.fetch(pair.narrow, start_at))
    wide_bytes = len(orjson.dumps(wide_rows))
    narrow_bytes = len(orjson.dumps(narrow_rows))
    wide_p95 = _p95([sample.elapsed_ms for sample in wide_samples])
    narrow_p95 = _p95([sample.elapsed_ms for sample in narrow_samples])
    wide_blocks = max(sample.buffer_blocks for sample in wide_samples)
    narrow_blocks = max(sample.buffer_blocks for sample in narrow_samples)
    return {
        'wide_p95_ms': round(wide_p95, 3),
        'narrow_p95_ms': round(narrow_p95, 3),
        'p95_ratio': round(narrow_p95 / wide_p95, 3),
        'wide_buffer_blocks': wide_blocks,
        'narrow_buffer_blocks': narrow_blocks,
        'wide_payload_bytes': wide_bytes,
        'narrow_payload_bytes': narrow_bytes,
        'payload_ratio': round(narrow_bytes / wide_bytes, 3),
        'row_count_equal': len(wide_rows) == len(narrow_rows),
    }


async def _execute(args: argparse.Namespace) -> tuple[dict[str, object], bool]:
    profile = PROFILES[args.profile]
    postgres_url = _test_postgres_url(str(args.postgres_url))
    end_at = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start_at = end_at - timedelta(hours=profile.hours)
    connection = await asyncpg.connect(dsn=postgres_url)
    try:
        await _prepare_tables(connection, profile, end_at)
        queries = {name: await _query_report(connection, pair, start_at) for name, pair in QUERIES.items()}
    finally:
        await connection.close()
    success = all(
        report['p95_ratio'] <= MAX_P95_RATIO
        and report['payload_ratio'] <= PAYLOAD_BUDGETS[name]
        and report['narrow_buffer_blocks'] <= report['wide_buffer_blocks']
        and report['row_count_equal']
        for name, report in queries.items()
    )
    result: dict[str, object] = {
        'success': success,
        'profile': args.profile,
        'gateway_rows': profile.gateways * profile.hours,
        'method_rows': profile.gateways * profile.methods * profile.hours,
        'budgets': {'max_p95_ratio': MAX_P95_RATIO, 'max_payload_ratios': PAYLOAD_BUDGETS},
        'queries': queries,
    }
    return result, success


def main() -> None:
    report, success = asyncio.run(_execute(_parse_args()))
    print(orjson.dumps(report, option=orjson.OPT_INDENT_2).decode())
    if not success:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
