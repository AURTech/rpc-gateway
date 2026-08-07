import asyncio
from threading import Event

import pytest
from app.services.auth import password as password_service
from app.services.auth.password import PasswordWorker, PasswordWorkLimitError, hash_password, verify_password


def test_hash_password_round_trip() -> None:
    stored = hash_password('correct-horse-battery')

    assert stored != 'correct-horse-battery'
    assert verify_password('correct-horse-battery', stored) is True


def test_verify_password_rejects_wrong_value() -> None:
    stored = hash_password('correct-horse-battery')

    assert verify_password('wrong-value', stored) is False


def test_verify_password_handles_malformed_hash() -> None:
    assert verify_password('anything', 'not-a-valid-hash') is False
    assert verify_password('anything', '') is False


@pytest.mark.anyio
async def test_password_worker_uses_dummy_hash_when_account_has_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    verified_hashes: list[str] = []

    def fake_verify(raw: str, stored: str) -> bool:
        assert raw == 'candidate-password'
        verified_hashes.append(stored)
        return True

    monkeypatch.setattr(password_service, 'verify_password', fake_verify)
    worker = PasswordWorker(max_concurrency=1)

    assert await worker.verify('candidate-password', None) is False
    assert verified_hashes == [password_service._DUMMY_PASSWORD_HASH]


@pytest.mark.anyio
async def test_password_worker_rejects_work_above_concurrency_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    started = Event()
    release = Event()

    def slow_verify(raw: str, stored: str) -> bool:
        _ = raw
        _ = stored
        started.set()
        release.wait(timeout=5)
        return True

    monkeypatch.setattr(password_service, 'verify_password', slow_verify)
    worker = PasswordWorker(max_concurrency=1)
    first = asyncio.create_task(worker.verify('first', 'stored'))
    try:
        while not started.is_set():
            await asyncio.sleep(0)

        with pytest.raises(PasswordWorkLimitError, match='capacity'):
            await worker.verify('second', 'stored')
    finally:
        release.set()

    assert await first is True
