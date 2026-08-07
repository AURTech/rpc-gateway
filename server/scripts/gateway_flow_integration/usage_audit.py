import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg
from app.infra.db import TORTOISE_ORM
from app.model.blockchain import Chain, Network
from app.model.usage import GatewayUsageEvent
from app.services.base import Manager
from app.services.usage import GatewayUsageBuffer, GatewayUsageIngestManager
from redis.asyncio import Redis
from scripts.gateway_flow_integration.client import GatewayClient
from tortoise import Tortoise

_METRIC_FIELDS = (
    'total_requests',
    'successful_requests',
    'failed_requests',
    'total_duration_ms',
    'total_request_bytes',
    'total_response_bytes',
    'cache_eligible_requests',
    'cache_hit_requests',
)

type UsageMetrics = dict[str, int]
type GatewayScope = tuple[str, str, str, str, str, datetime]
type MethodScope = tuple[str, str, str, str, str, str, datetime]
type UsageIdentity = tuple[str, str, str, Chain, Network, str, bool, bool, bool]


@dataclass(frozen=True, slots=True, kw_only=True)
class UsageCallSpec:
    account_id: str
    app_id: str
    gateway_id: str
    chain: Chain
    network: Network
    method: str
    successful: bool
    cache_eligible: bool = False
    cache_hit: bool = False


def _empty_metrics() -> UsageMetrics:
    return dict.fromkeys(_METRIC_FIELDS, 0)


def _event_metrics(event: GatewayUsageEvent) -> UsageMetrics:
    return {
        'total_requests': 1,
        'successful_requests': int(event.successful),
        'failed_requests': int(not event.successful),
        'total_duration_ms': event.duration_ms,
        'total_request_bytes': event.request_bytes,
        'total_response_bytes': event.response_bytes,
        'cache_eligible_requests': int(event.cache_eligible),
        'cache_hit_requests': int(event.cache_hit),
    }


def _add_metrics(target: UsageMetrics, source: UsageMetrics) -> None:
    for field in _METRIC_FIELDS:
        target[field] += source[field]


def _aggregate(events: Iterable[GatewayUsageEvent]) -> UsageMetrics:
    total = _empty_metrics()
    for event in events:
        _add_metrics(total, _event_metrics(event))
    return total


def _bucket_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _spec_identity(spec: UsageCallSpec) -> UsageIdentity:
    return (
        spec.account_id,
        spec.app_id,
        spec.gateway_id,
        spec.chain,
        spec.network,
        spec.method,
        spec.successful,
        spec.cache_eligible,
        spec.cache_hit,
    )


def _event_identity(event: GatewayUsageEvent) -> UsageIdentity:
    return (
        event.account_id,
        event.app_id,
        event.gateway_id,
        event.chain,
        event.network,
        event.method,
        event.successful,
        event.cache_eligible,
        event.cache_hit,
    )


def _assert_metric_invariants(metrics: UsageMetrics) -> None:
    if metrics['successful_requests'] + metrics['failed_requests'] != metrics['total_requests']:
        raise RuntimeError(f'Usage outcome invariant failed: {metrics!r}.')
    if not (metrics['cache_hit_requests'] <= metrics['cache_eligible_requests'] <= metrics['total_requests']):
        raise RuntimeError(f'Usage cache invariant failed: {metrics!r}.')


def _assert_api_metrics(payload: dict[str, Any], expected: UsageMetrics) -> None:
    actual = {field: int(payload[field]) for field in _METRIC_FIELDS}
    if actual != expected:
        raise RuntimeError(f'Usage API metrics mismatch: expected {expected!r}, found {actual!r}.')
    _assert_metric_invariants(actual)
    total = expected['total_requests']
    eligible = expected['cache_eligible_requests']
    derived = {
        'success_rate': expected['successful_requests'] / total if total else 0,
        'avg_duration_ms': expected['total_duration_ms'] / total if total else 0,
        'total_traffic_bytes': expected['total_request_bytes'] + expected['total_response_bytes'],
        'cache_hit_rate': expected['cache_hit_requests'] / eligible if eligible else 0,
    }
    for field, value in derived.items():
        if not math.isclose(float(payload[field]), value, rel_tol=1e-12, abs_tol=1e-12):
            raise RuntimeError(f'Usage API derived metric {field} mismatch: expected {value}, found {payload[field]!r}.')


def _sum_points(points: Any) -> UsageMetrics:
    if not isinstance(points, list):
        raise RuntimeError('Usage API points are invalid.')
    total = _empty_metrics()
    for point in points:
        if not isinstance(point, dict):
            raise RuntimeError('Usage API point is invalid.')
        values = _empty_metrics()
        for field in _METRIC_FIELDS:
            value = point.get(field)
            if not isinstance(value, int):
                raise RuntimeError(f'Usage API point metric {field} is invalid: {value!r}.')
            values[field] = value
        _add_metrics(total, values)
    return total


class UsageAuditor:
    def __init__(self, redis_url: str, postgres_url: str) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True, retry_on_timeout=False)
        self._postgres_url = postgres_url

    async def close(self) -> None:
        await self._redis.aclose()

    async def reset(self) -> dict[str, int]:
        await self._redis.delete(
            GatewayUsageBuffer.stream_key(),
            GatewayUsageBuffer.dropped_key(),
            GatewayUsageBuffer.flush_lease_key(),
            GatewayUsageBuffer.retention_lease_key(),
        )
        connection = await asyncpg.connect(self._postgres_url)
        try:
            deleted_methods = int(
                await connection.fetchval(
                    'WITH rows AS (DELETE FROM gateway_usage_method_hourly RETURNING 1) SELECT COUNT(*) FROM rows'
                )
            )
            deleted_gateways = int(
                await connection.fetchval(
                    'WITH rows AS (DELETE FROM gateway_usage_hourly RETURNING 1) SELECT COUNT(*) FROM rows'
                )
            )
            deleted_checkpoints = int(
                await connection.fetchval(
                    'WITH rows AS (DELETE FROM gateway_usage_checkpoint RETURNING 1) SELECT COUNT(*) FROM rows'
                )
            )
        finally:
            await connection.close()
        return {
            'deleted_gateway_rows': deleted_gateways,
            'deleted_method_rows': deleted_methods,
            'deleted_checkpoints': deleted_checkpoints,
        }

    async def load_app_identity(self, app_id: str) -> tuple[str, str]:
        connection = await asyncpg.connect(self._postgres_url)
        try:
            row = await connection.fetchrow(
                'SELECT account_id, id FROM app WHERE id = $1 AND deleted_at IS NULL',
                app_id,
            )
        finally:
            await connection.close()
        if row is None:
            raise RuntimeError(f'Usage App identity is missing: {app_id}.')
        return str(row['account_id']), str(row['id'])

    async def audit_stream(
        self,
        expected: list[UsageCallSpec],
        *,
        minimum_capture_ratio: float = 0.98,
    ) -> tuple[list[GatewayUsageEvent], dict[str, object]]:
        rows = await self._redis.xrange(GatewayUsageBuffer.stream_key(), min='-', max='+')
        stream_length = int(await self._redis.xlen(GatewayUsageBuffer.stream_key()))
        if len(rows) != stream_length:
            raise RuntimeError(f'Usage Stream read mismatch: XLEN={stream_length}, rows={len(rows)}.')
        expected_counts = Counter(_spec_identity(spec) for spec in expected)
        actual_counts: Counter[UsageIdentity] = Counter()
        events: list[GatewayUsageEvent] = []
        stream_ids: set[str] = set()
        event_ids: set[str] = set()
        methods: set[str] = set()
        for raw_stream_id, values in rows:
            stream_id = str(raw_stream_id)
            payload = values.get('payload')
            if stream_id in stream_ids or not isinstance(payload, str | bytes):
                raise RuntimeError(f'Usage Stream entry is duplicated or malformed: {stream_id}.')
            stream_ids.add(stream_id)
            event = GatewayUsageEvent.model_validate_json(payload)
            if event.event_id in event_ids:
                raise RuntimeError(f'Usage event is duplicated: {event.event_id}.')
            event_ids.add(event.event_id)
            methods.add(event.method)
            identity = _event_identity(event)
            actual_counts[identity] += 1
            if actual_counts[identity] > expected_counts[identity]:
                raise RuntimeError(f'Usage Stream contains an unexpected event identity: {identity!r}.')
            _assert_metric_invariants(_event_metrics(event))
            events.append(event)

        sent = len(expected)
        captured = len(events)
        minimum_captured = math.ceil(sent * minimum_capture_ratio)
        if captured > sent or captured < minimum_captured:
            raise RuntimeError(
                f'Usage capture ratio is outside the allowed boundary: sent={sent}, captured={captured}, '
                f'minimum={minimum_captured}.'
            )
        lost = sent - captured
        dropped_value = await self._redis.get(GatewayUsageBuffer.dropped_key())
        dropped = int(dropped_value or 0)
        if dropped > lost:
            raise RuntimeError(f'Usage dropped counter exceeds observed loss: dropped={dropped}, lost={lost}.')
        return events, {
            'sent': sent,
            'captured': captured,
            'lost': lost,
            'loss_rate': lost / sent if sent else 0,
            'minimum_capture_ratio': minimum_capture_ratio,
            'stream_ids_unique': len(stream_ids),
            'event_ids_unique': len(event_ids),
            'methods_unique': len(methods),
            'cache_eligible': sum(int(event.cache_eligible) for event in events),
            'cache_hits': sum(int(event.cache_hit) for event in events),
            'dropped_counter': dropped,
        }

    async def drain(self, expected_entries: int) -> dict[str, int | float | bool | None]:
        await Tortoise.init(config=TORTOISE_ORM)
        Manager.set_redis(self._redis)
        try:
            result = await GatewayUsageIngestManager.drain(
                batch_size=500,
                max_batches=20,
                max_seconds=30,
                lease_seconds=45,
            )
        finally:
            Manager.clear_redis()
            await Tortoise.close_connections()
        expected_values = {
            'received': expected_entries,
            'inserted': expected_entries,
            'acknowledged': expected_entries,
            'invalid': 0,
            'remaining_entries': 0,
        }
        actual_values = {
            'received': result['received'],
            'inserted': result['inserted'],
            'acknowledged': result['acknowledged'],
            'invalid': result['invalid'],
            'remaining_entries': result['remaining_entries'],
        }
        if result['lock_acquired'] is not True or actual_values != expected_values:
            raise RuntimeError(f'Usage drain did not converge exactly: expected {expected_values!r}, found {result!r}.')
        if int(await self._redis.xlen(GatewayUsageBuffer.stream_key())) != 0:
            raise RuntimeError('Usage Stream is not empty after drain.')
        return {
            'lock_acquired': result['lock_acquired'],
            'batches': result['batches'],
            'received': result['received'],
            'inserted': result['inserted'],
            'acknowledged': result['acknowledged'],
            'invalid': result['invalid'],
            'remaining_entries': result['remaining_entries'],
            'oldest_age_seconds': result['oldest_age_seconds'],
            'limited': result['limited'],
            'timed_out': result['timed_out'],
        }

    async def audit_database(self, events: list[GatewayUsageEvent]) -> dict[str, object]:
        expected_gateways: dict[GatewayScope, UsageMetrics] = {}
        expected_methods: dict[MethodScope, UsageMetrics] = {}
        for event in events:
            bucket = _bucket_hour(event.started_at)
            gateway_scope = (
                event.account_id,
                event.app_id,
                event.gateway_id,
                event.chain.value,
                event.network.value,
                bucket,
            )
            method_scope = (
                event.account_id,
                event.app_id,
                event.gateway_id,
                event.chain.value,
                event.network.value,
                event.method,
                bucket,
            )
            _add_metrics(expected_gateways.setdefault(gateway_scope, _empty_metrics()), _event_metrics(event))
            _add_metrics(expected_methods.setdefault(method_scope, _empty_metrics()), _event_metrics(event))

        connection = await asyncpg.connect(self._postgres_url)
        try:
            gateway_rows = await connection.fetch(
                'SELECT account_id, app_id, gateway_id, chain, network, bucket_hour, '
                + ', '.join(_METRIC_FIELDS)
                + ' FROM gateway_usage_hourly'
            )
            method_rows = await connection.fetch(
                'SELECT account_id, app_id, gateway_id, chain, network, method, bucket_hour, '
                + ', '.join(_METRIC_FIELDS)
                + ' FROM gateway_usage_method_hourly'
            )
            checkpoint = await connection.fetchrow('SELECT id, last_stream_id FROM gateway_usage_checkpoint')
        finally:
            await connection.close()

        actual_gateways: dict[GatewayScope, UsageMetrics] = {}
        for row in gateway_rows:
            gateway_scope: GatewayScope = (
                str(row['account_id']),
                str(row['app_id']),
                str(row['gateway_id']),
                str(row['chain']),
                str(row['network']),
                row['bucket_hour'],
            )
            actual_gateways[gateway_scope] = {field: int(row[field]) for field in _METRIC_FIELDS}
        actual_methods: dict[MethodScope, UsageMetrics] = {}
        for row in method_rows:
            method_scope: MethodScope = (
                str(row['account_id']),
                str(row['app_id']),
                str(row['gateway_id']),
                str(row['chain']),
                str(row['network']),
                str(row['method']),
                row['bucket_hour'],
            )
            actual_methods[method_scope] = {field: int(row[field]) for field in _METRIC_FIELDS}
        if actual_gateways != expected_gateways:
            raise RuntimeError('Gateway Usage hourly rows do not exactly match captured Stream events.')
        if actual_methods != expected_methods:
            raise RuntimeError('Gateway Usage method rows do not exactly match captured Stream events.')
        checkpoint_id = str(checkpoint['id']).rstrip() if checkpoint is not None else ''
        if checkpoint is None or checkpoint_id != 'usage-v3-checkpoint' or checkpoint['last_stream_id'] == '0-0':
            raise RuntimeError(f'Usage checkpoint did not advance: {checkpoint!r}.')
        for metrics in [*actual_gateways.values(), *actual_methods.values()]:
            _assert_metric_invariants(metrics)
        return {
            'gateway_rows': len(actual_gateways),
            'method_rows': len(actual_methods),
            'checkpoint': str(checkpoint['last_stream_id']),
            'aggregated_events': sum(metrics['total_requests'] for metrics in actual_gateways.values()),
        }

    async def audit_api(
        self,
        clients: list[tuple[GatewayClient, str, str, str]],
        events: list[GatewayUsageEvent],
    ) -> dict[str, object]:
        reports: list[dict[str, object]] = []
        for client, account_id, app_id, foreign_app_id in clients:
            account_events = [event for event in events if event.account_id == account_id]
            expected_total = _aggregate(account_events)
            summary = await client.get_usage('summary', {'time_range': 'daily'})
            _assert_api_metrics(summary, expected_total)
            scoped = await client.get_usage('summary', {'time_range': 'daily', 'app_id': app_id})
            _assert_api_metrics(scoped, expected_total)
            foreign = await client.get_usage('summary', {'time_range': 'daily', 'app_id': foreign_app_id})
            _assert_api_metrics(foreign, _empty_metrics())

            series = await client.get_usage('series', {'time_range': 'daily', 'app_id': app_id})
            series_metrics = _sum_points(series.get('items'))
            if series_metrics != expected_total:
                raise RuntimeError('Usage series does not match the captured account events.')

            methods = await client.get_usage('methods', {'time_range': 'daily', 'app_id': app_id, 'limit': 500})
            expected_methods: dict[str, UsageMetrics] = {}
            for event in account_events:
                _add_metrics(expected_methods.setdefault(event.method, _empty_metrics()), _event_metrics(event))
            method_items = methods.get('items')
            if not isinstance(method_items, list):
                raise RuntimeError('Usage methods response is invalid.')
            actual_methods = {str(item['method']): _sum_points(item['points']) for item in method_items}
            if actual_methods != expected_methods:
                raise RuntimeError('Usage methods response does not match captured methods.')

            networks = await client.get_usage('networks', {'time_range': 'daily', 'app_id': app_id, 'limit': 500})
            expected_networks: dict[tuple[str, str], UsageMetrics] = {}
            for event in account_events:
                dimension = (event.chain.value, event.network.value)
                _add_metrics(expected_networks.setdefault(dimension, _empty_metrics()), _event_metrics(event))
            network_items = networks.get('items')
            if not isinstance(network_items, list):
                raise RuntimeError('Usage networks response is invalid.')
            actual_networks = {
                (str(item['chain']), str(item['network'])): _sum_points(item['points']) for item in network_items
            }
            if actual_networks != expected_networks:
                raise RuntimeError('Usage networks response does not match captured network dimensions.')

            reports.append(
                {
                    'account_id': account_id,
                    'app_id': app_id,
                    'events': len(account_events),
                    'methods': len(actual_methods),
                    'networks': len(actual_networks),
                    'foreign_app_total': int(foreign['total_requests']),
                }
            )
        return {'accounts': reports, 'endpoints_verified': 4 * len(reports)}
