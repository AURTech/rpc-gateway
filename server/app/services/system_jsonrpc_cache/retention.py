import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass

from app.model.blockchain import Chain
from app.services.system_jsonrpc_cache.interface import RetentionStore
from app.services.system_jsonrpc_cache.limits import (
    RETENTION_CLEANUP_BATCH_ROWS,
    RETENTION_CLEANUP_BATCH_TIMEOUT_SECONDS,
    RETENTION_CLEANUP_MAX_BATCHES,
    RETENTION_CLEANUP_TIME_BUDGET_SECONDS,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetentionCleanupResult:
    deleted_rows: int
    deleted_bytes: int
    attempted_batches: int
    completed_batches: int
    timed_out_chains: tuple[Chain, ...]
    elapsed_ms: int


class RetentionManager:
    def __init__(self, store: RetentionStore, retention_seconds: Mapping[Chain, int], *, max_batch_bytes: int) -> None:
        if set(retention_seconds) != set(Chain):
            raise ValueError('System JSON-RPC Cache PostgreSQL retention must define every supported chain.')
        if isinstance(max_batch_bytes, bool) or max_batch_bytes < 1:
            raise ValueError('System JSON-RPC Cache PostgreSQL cleanup byte limit must be positive.')
        self._store = store
        self._retention_seconds = dict(retention_seconds)
        self._max_batch_bytes = max_batch_bytes

    async def delete_expired(self, *, start_offset: int = 0) -> RetentionCleanupResult:
        """Delete bounded PostgreSQL retention batches while isolating chain timeouts from the cleanup round."""
        if isinstance(start_offset, bool) or start_offset < 0:
            raise ValueError('PostgreSQL retention cleanup start offset must be non-negative.')
        started_at = time.monotonic()
        chains = tuple(sorted(self._retention_seconds, key=lambda chain: chain.value))
        offset = start_offset % len(chains)
        chains = chains[offset:] + chains[:offset]
        drained: set[Chain] = set()
        timed_out: set[Chain] = set()
        deleted_rows = 0
        deleted_bytes = 0
        attempted_batches = 0
        completed_batches = 0
        chain_offset = 0
        while attempted_batches < RETENTION_CLEANUP_MAX_BATCHES and len(drained) + len(timed_out) < len(chains):
            remaining_seconds = RETENTION_CLEANUP_TIME_BUDGET_SECONDS - (time.monotonic() - started_at)
            if remaining_seconds <= 0:
                break
            chain = chains[chain_offset % len(chains)]
            chain_offset += 1
            if chain in drained or chain in timed_out:
                continue
            attempted_batches += 1
            try:
                async with asyncio.timeout(min(RETENTION_CLEANUP_BATCH_TIMEOUT_SECONDS, remaining_seconds)):
                    batch = await self._store.delete_expired(
                        chain,
                        self._retention_seconds[chain],
                        max_rows=RETENTION_CLEANUP_BATCH_ROWS,
                        max_bytes=self._max_batch_bytes,
                    )
            except TimeoutError:
                timed_out.add(chain)
                continue
            completed_batches += 1
            deleted_rows += batch.deleted_rows
            deleted_bytes += batch.deleted_bytes
            if not batch.has_more:
                drained.add(chain)
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        return RetentionCleanupResult(
            deleted_rows=deleted_rows,
            deleted_bytes=deleted_bytes,
            attempted_batches=attempted_batches,
            completed_batches=completed_batches,
            timed_out_chains=tuple(chain for chain in chains if chain in timed_out),
            elapsed_ms=elapsed_ms,
        )
