from app.core.usage import DEFAULT_USAGE_STREAM_MAX_LENGTH
from scripts.usage_memory_stress import _max_event


def test_memory_probe_uses_max_utf8_event() -> None:
    event = _max_event()
    payload = event.model_dump_json(exclude_defaults=True).encode()

    assert DEFAULT_USAGE_STREAM_MAX_LENGTH == 250_000
    assert len(event.method) == 256
    assert len(event.method.encode()) == 1024
    assert len(payload) >= 1400
