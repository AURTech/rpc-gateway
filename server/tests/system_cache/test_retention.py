from collections import deque
from collections.abc import Mapping, Sequence

import pytest
from app.model.blockchain import Chain
from app.services.system_cache import retention as retention_module
from app.services.system_cache.interface import RetentionDeleteResult
from app.services.system_cache.retention import RetentionManager

pytestmark = pytest.mark.anyio


class _Store:
    def __init__(self, results: Mapping[Chain, Sequence[RetentionDeleteResult | Exception]] | None = None) -> None:
        self._results = {chain: deque(chain_results) for chain, chain_results in (results or {}).items()}
        self.calls: list[tuple[Chain, int, int, int]] = []

    async def delete_expired(
        self,
        chain: Chain,
        retention_seconds: int,
        *,
        max_rows: int,
        max_bytes: int,
    ) -> RetentionDeleteResult:
        self.calls.append((chain, retention_seconds, max_rows, max_bytes))
        results = self._results.get(chain)
        result = results.popleft() if results else RetentionDeleteResult(deleted_rows=0, deleted_bytes=0, has_more=False)
        if isinstance(result, Exception):
            raise result
        return result


def _manager(store: _Store) -> RetentionManager:
    return RetentionManager(store, dict.fromkeys(Chain, 3600), max_batch_bytes=32)


async def test_timeout_skips_chain_and_continues_round() -> None:
    chains = tuple(sorted(Chain, key=lambda chain: chain.value))
    store = _Store({chains[0]: [TimeoutError()]})

    result = await _manager(store).delete_expired()

    assert [call[0] for call in store.calls] == list(chains)
    assert all(call[1:] == (3600, 64, 32) for call in store.calls)
    assert result.attempted_batches == len(chains)
    assert result.completed_batches == len(chains) - 1
    assert result.timed_out_chains == (chains[0],)


async def test_has_more_keeps_short_byte_bounded_batch_active() -> None:
    chain = min(Chain, key=lambda item: item.value)
    store = _Store(
        {
            chain: [
                RetentionDeleteResult(deleted_rows=2, deleted_bytes=32, has_more=True),
                RetentionDeleteResult(deleted_rows=1, deleted_bytes=16, has_more=False),
            ]
        }
    )

    result = await _manager(store).delete_expired()

    assert [call[0] for call in store.calls].count(chain) == 2
    assert result.deleted_rows == 3
    assert result.deleted_bytes == 48
    assert result.attempted_batches == len(Chain) + 1
    assert result.completed_batches == len(Chain) + 1
    assert not result.timed_out_chains


async def test_start_offset_rotates_first_chain() -> None:
    chains = tuple(sorted(Chain, key=lambda chain: chain.value))
    store = _Store()

    await _manager(store).delete_expired(start_offset=1)

    assert [call[0] for call in store.calls] == list(chains[1:] + chains[:1])


async def test_cleanup_stops_at_attempt_limit() -> None:
    pending = RetentionDeleteResult(deleted_rows=1, deleted_bytes=1, has_more=True)
    store = _Store({chain: [pending] * 4 for chain in Chain})

    result = await _manager(store).delete_expired()

    assert result.attempted_batches == 32
    assert result.completed_batches == 32
    assert result.deleted_rows == 32


async def test_cleanup_stops_at_time_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retention_module, 'RETENTION_CLEANUP_TIME_BUDGET_SECONDS', -1)
    store = _Store()

    result = await _manager(store).delete_expired()

    assert not store.calls
    assert result.attempted_batches == 0
    assert result.elapsed_ms >= 0
