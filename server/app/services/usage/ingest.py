import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from fastlog import log

from app.core.config import CONF
from app.infra.db import in_tx
from app.infra.redis import acquire_redis_lease
from app.model.usage import GatewayUsageEvent
from app.services.usage.buffer import BufferedUsageEvent, GatewayUsageBuffer
from app.services.usage.store import GatewayUsageStore, UsageAggregate, UsagePartitionResult, UsageScope
from app.util.datetime import floor_utc_five_minutes, floor_utc_hour

METHODS_PER_GATEWAY_HOUR = 500
OTHER_METHOD = '__other__'

MethodAggregateKey = tuple[str, str, str, str, str, str, datetime]
FineAggregateKey = tuple[str, str, str, str, str, datetime]
FineMethodAggregateKey = tuple[str, str, str, str, str, str, datetime]


@dataclass(slots=True, kw_only=True)
class UsageRows:
    gateway_hourly: dict[UsageScope, UsageAggregate]
    method_hourly: dict[MethodAggregateKey, UsageAggregate]
    gateway_fine: dict[FineAggregateKey, UsageAggregate]
    method_fine: dict[FineMethodAggregateKey, UsageAggregate]
    rollup_hours: set[datetime]


class GatewayUsageDrainResult(TypedDict):
    lock_acquired: bool
    batches: int
    received: int
    inserted: int
    acknowledged: int
    invalid: int
    remaining_entries: int
    oldest_age_seconds: float | None
    limited: bool
    timed_out: bool


class GatewayUsageIngestManager:
    @staticmethod
    def _event_scope(event: GatewayUsageEvent) -> UsageScope:
        return (
            event.account_id,
            event.app_id,
            event.gateway_id,
            event.chain.value,
            event.network.value,
            floor_utc_hour(event.started_at),
        )

    @staticmethod
    def _fine_scope(event: GatewayUsageEvent) -> FineAggregateKey:
        return (
            event.account_id,
            event.app_id,
            event.gateway_id,
            event.chain.value,
            event.network.value,
            floor_utc_five_minutes(event.started_at),
        )

    @classmethod
    def _aggregate_rows(
        cls,
        events: list[BufferedUsageEvent],
        known_methods: dict[UsageScope, set[str]],
        *,
        now: datetime | None = None,
    ) -> UsageRows:
        gateway_hourly: dict[UsageScope, UsageAggregate] = {}
        method_hourly: dict[MethodAggregateKey, UsageAggregate] = {}
        gateway_fine: dict[FineAggregateKey, UsageAggregate] = {}
        method_fine: dict[FineMethodAggregateKey, UsageAggregate] = {}
        rollup_hours: set[datetime] = set()
        cutover_at = CONF.USAGE_ASYNC_ROLLUP_CUTOVER_AT
        reference_at = now or datetime.now(UTC)
        fine_cutoff = reference_at - timedelta(hours=CONF.USAGE_FINE_RETENTION_HOURS)
        for buffered in events:
            event = buffered.event
            scope = cls._event_scope(event)
            fine_scope = cls._fine_scope(event)
            methods = known_methods.setdefault(scope, set())
            method = event.method
            if method != OTHER_METHOD and method not in methods:
                if len(methods) < METHODS_PER_GATEWAY_HOUR:
                    methods.add(method)
                else:
                    method = OTHER_METHOD
            uses_fine = event.started_at >= fine_cutoff
            if uses_fine:
                fine_gateway_values = gateway_fine.setdefault(fine_scope, UsageAggregate())
                fine_method_values = method_fine.setdefault((*fine_scope[:5], method, fine_scope[5]), UsageAggregate())
                cls._add_event(fine_gateway_values, event)
                cls._add_event(fine_method_values, event)
            if uses_fine and cutover_at is not None and event.started_at >= cutover_at:
                rollup_hours.add(scope[5])
                continue
            hourly_gateway_values = gateway_hourly.setdefault(scope, UsageAggregate())
            hourly_method_values = method_hourly.setdefault((*scope[:5], method, scope[5]), UsageAggregate())
            cls._add_event(hourly_gateway_values, event)
            cls._add_event(hourly_method_values, event)
        return UsageRows(
            gateway_hourly=gateway_hourly,
            method_hourly=method_hourly,
            gateway_fine=gateway_fine,
            method_fine=method_fine,
            rollup_hours=rollup_hours,
        )

    @staticmethod
    def _add_event(values: UsageAggregate, event: GatewayUsageEvent) -> None:
        values.total_requests += 1
        values.successful_requests += int(event.successful)
        values.failed_requests += int(not event.successful)
        values.total_duration_ms += event.duration_ms
        values.total_request_bytes += event.request_bytes
        values.total_response_bytes += event.response_bytes
        values.cache_eligible_requests += int(event.cache_eligible)
        values.cache_hit_requests += int(event.cache_hit)

    @classmethod
    async def _flush_batch(cls, *, count: int) -> tuple[int, int, int, int, int]:
        """Commit aggregates and the Stream checkpoint together before deleting Redis entries."""
        async with in_tx() as connection:
            checkpoint = await GatewayUsageStore.lock_checkpoint(connection)
            try:
                await GatewayUsageBuffer.delete_checkpointed(checkpoint=checkpoint.last_stream_id, count=count)
            except Exception as exc:
                log.warning(
                    f'Gateway Usage processed Stream cleanup failed | Checkpoint:{checkpoint.last_stream_id} | Error:{exc!r}'
                )
            batch = await GatewayUsageBuffer.read_batch(after_id=checkpoint.last_stream_id, count=count)
            if not batch.stream_ids:
                return 0, 0, 0, 0, 0
            if batch.events:
                scopes = {cls._event_scope(buffered.event) for buffered in batch.events}
                known_methods = await GatewayUsageStore.get_known_methods(
                    connection,
                    scopes,
                    excluded_method=OTHER_METHOD,
                )
                rows = cls._aggregate_rows(batch.events, known_methods)
                await GatewayUsageStore.upsert_gateway_fine(connection, rows.gateway_fine)
                await GatewayUsageStore.upsert_method_fine(connection, rows.method_fine)
                await GatewayUsageStore.upsert_gateway_hourly(connection, rows.gateway_hourly)
                await GatewayUsageStore.upsert_method_hourly(connection, rows.method_hourly)
                await GatewayUsageStore.mark_rollup_hours(connection, rows.rollup_hours)
            await GatewayUsageStore.update_checkpoint(connection, checkpoint, batch.last_stream_id)

        try:
            acknowledged = await GatewayUsageBuffer.delete(batch.stream_ids)
        except Exception as exc:
            acknowledged = 0
            log.warning(f'Gateway Usage committed but Stream delete failed | Checkpoint:{batch.last_stream_id} | Error:{exc!r}')
        return len(batch.stream_ids), len(batch.events), len(batch.events), acknowledged, batch.invalid

    @classmethod
    async def drain(
        cls,
        *,
        batch_size: int,
        max_batches: int,
        max_seconds: int,
        lease_seconds: int,
    ) -> GatewayUsageDrainResult:
        """Drain bounded usage batches while a renewable process-shared lease is owned."""
        if lease_seconds <= max_seconds:
            raise ValueError('Gateway Usage flush lease must exceed the drain time limit.')
        lease = await acquire_redis_lease(
            GatewayUsageBuffer.redis,
            GatewayUsageBuffer.flush_lease_key(),
            ttl_seconds=lease_seconds,
        )
        if lease is None:
            backlog = await GatewayUsageBuffer.get_backlog()
            return {
                'lock_acquired': False,
                'batches': 0,
                'received': 0,
                'inserted': 0,
                'acknowledged': 0,
                'invalid': 0,
                'remaining_entries': backlog.entries,
                'oldest_age_seconds': backlog.oldest_age_seconds,
                'limited': False,
                'timed_out': False,
            }

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_seconds
        batches = 0
        received = 0
        inserted = 0
        acknowledged = 0
        invalid = 0
        timed_out = False
        batch_limited = False
        try:
            while batches < max_batches:
                try:
                    async with asyncio.timeout_at(deadline):
                        if not await lease.renew():
                            break
                        processed, batch_received, batch_inserted, batch_acknowledged, batch_invalid = await cls._flush_batch(
                            count=batch_size
                        )
                except TimeoutError:
                    timed_out = True
                    break
                if processed == 0:
                    break
                batches += 1
                received += batch_received
                inserted += batch_inserted
                acknowledged += batch_acknowledged
                invalid += batch_invalid
                if processed < batch_size:
                    break
            else:
                batch_limited = True
            backlog = await GatewayUsageBuffer.get_backlog()
            return {
                'lock_acquired': True,
                'batches': batches,
                'received': received,
                'inserted': inserted,
                'acknowledged': acknowledged,
                'invalid': invalid,
                'remaining_entries': backlog.entries,
                'oldest_age_seconds': backlog.oldest_age_seconds,
                'limited': batch_limited and backlog.entries > 0,
                'timed_out': timed_out,
            }
        finally:
            try:
                await lease.release()
            except Exception as exc:
                log.warning(f'Gateway Usage flush lease release failed | Error:{exc!r}')

    @staticmethod
    async def maintain_partitions(*, now: datetime | None = None) -> UsagePartitionResult:
        reference_at = now or datetime.now(UTC)
        return await GatewayUsageStore.maintain_partitions(reference_at)
