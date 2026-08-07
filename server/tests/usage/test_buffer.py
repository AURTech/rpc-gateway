import asyncio
from datetime import UTC, datetime

import pytest
from app.model.blockchain import Chain, Network
from app.model.usage import GatewayUsageEvent
from app.services.usage.buffer import (
    APPEND_BATCH_IF_CAPACITY_SCRIPT,
    APPEND_IF_CAPACITY_SCRIPT,
    GatewayUsageBuffer,
    GatewayUsageRecorder,
)


class _FullRedis:
    def __init__(self) -> None:
        self.args: tuple[object, ...] = ()

    async def eval(self, *args: object) -> int | bool:
        self.args = args
        return False


class _PartialRedis(_FullRedis):
    async def eval(self, *args: object) -> int:
        self.args = args
        return 1


def _event() -> GatewayUsageEvent:
    return GatewayUsageEvent(
        event_id='a' * 32,
        account_id='account-1',
        app_id='app-1',
        gateway_id='gateway-1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='eth_blockNumber',
        started_at=datetime.now(UTC),
        successful=True,
        duration_ms=1,
    )


def test_default_fields_are_omitted_without_changing_event() -> None:
    event = _event()

    payload = event.model_dump_json(exclude_defaults=True)

    assert len(payload) < len(event.model_dump_json())
    assert GatewayUsageEvent.model_validate_json(payload) == event


@pytest.mark.anyio
async def test_recorder_write_failure_does_not_block_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    attempted = asyncio.Event()

    async def fail(_events: list[GatewayUsageEvent]) -> int:
        attempted.set()
        raise ConnectionError('unavailable')

    monkeypatch.setattr(GatewayUsageBuffer, 'append_many', fail)
    event = _event()
    recorder = GatewayUsageRecorder()
    await recorder.start()

    assert recorder.submit(event)
    await asyncio.wait_for(attempted.wait(), timeout=1)
    await recorder.close(drain_seconds=0)


@pytest.mark.anyio
async def test_stream_full_rejects_event_and_uses_atomic_drop_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FullRedis()
    monkeypatch.setattr(GatewayUsageBuffer, '_redis', redis)
    event = _event()

    with pytest.raises(BufferError, match='Stream is full'):
        await GatewayUsageBuffer.append(event)

    assert redis.args[0] == APPEND_IF_CAPACITY_SCRIPT
    assert redis.args[1] == 2
    assert 'usage:v3:stream' in str(redis.args[2])
    assert 'usage:v3:dropped' in str(redis.args[3])
    assert redis.args[4] == 250_000
    assert isinstance(redis.args[5], str)
    assert redis.args[5].startswith('{')


@pytest.mark.anyio
async def test_batch_append_accepts_only_available_stream_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _PartialRedis()
    monkeypatch.setattr(GatewayUsageBuffer, '_redis', redis)

    written = await GatewayUsageBuffer.append_many([_event(), _event()])

    assert written == 1
    assert redis.args[0] == APPEND_BATCH_IF_CAPACITY_SCRIPT
    assert redis.args[1] == 2
    assert redis.args[4] == 250_000
    assert len(redis.args[5:]) == 2


@pytest.mark.anyio
async def test_recorder_close_drains_accepted_events(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[GatewayUsageEvent] = []

    async def append(events: list[GatewayUsageEvent]) -> int:
        written.extend(events)
        return len(events)

    monkeypatch.setattr(GatewayUsageBuffer, 'append_many', append)
    recorder = GatewayUsageRecorder()
    await recorder.start()
    events = [_event(), _event()]

    assert all(recorder.submit(event) for event in events)
    await recorder.close(drain_seconds=1)

    assert written == events
    assert recorder.pending == 0
