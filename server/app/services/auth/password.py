from anyio import CapacityLimiter, WouldBlock, to_thread
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()
_DUMMY_PASSWORD_HASH = '$argon2id$v=19$m=65536,t=3,p=4$i9yKYqCeOuEPwoUV5LP9tw$e7D3ONuqSmstVmi9IDu/WZUPQDOiXH9oMXRerFVojvU'


class PasswordWorkLimitError(RuntimeError):
    pass


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, stored: str) -> bool:
    try:
        return _hasher.verify(stored, raw)
    except (Argon2Error, ValueError):
        return False


class PasswordWorker:
    """Run Argon2 work off the event loop with a fail-fast per-process concurrency cap.

    AnyIO waits for a running worker thread when the caller is cancelled, so capacity is not released while CPU work
    is still executing.
    """

    def __init__(self, max_concurrency: int) -> None:
        self._limiter = CapacityLimiter(max_concurrency)

    async def hash(self, raw: str) -> str:
        self._acquire()
        try:
            return await to_thread.run_sync(hash_password, raw)
        finally:
            self._limiter.release()

    async def verify(self, raw: str, stored: str | None) -> bool:
        target_hash = stored or _DUMMY_PASSWORD_HASH
        self._acquire()
        try:
            matches = await to_thread.run_sync(verify_password, raw, target_hash)
        finally:
            self._limiter.release()
        return bool(stored) and matches

    def _acquire(self) -> None:
        try:
            self._limiter.acquire_nowait()
        except WouldBlock as exc:
            raise PasswordWorkLimitError('Password worker capacity is exhausted.') from exc
