from typing import Final

from app.model.endpoint import EndpointJsonRpcRequest

MAX_WAITERS: Final[int] = 2048
STALE_MS: Final[int] = 5000
STORE_TIMEOUT_SECONDS: Final[float] = 5
REDIS_IO_TIMEOUT_SECONDS: Final[float] = 1
FLIGHT_LEASE_MS: Final[int] = 5000
FLIGHT_HEARTBEAT_SECONDS: Final[float] = 1.0
COMMIT_CANCEL_TIMEOUT_SECONDS: Final[float] = 0.25
RETENTION_CLEANUP_INTERVAL_SECONDS: Final[int] = 30
RETENTION_CLEANUP_LEASE_SECONDS: Final[int] = 25
RETENTION_CLEANUP_TIME_BUDGET_SECONDS: Final[float] = 20
RETENTION_CLEANUP_BATCH_TIMEOUT_SECONDS: Final[float] = 5
RETENTION_CLEANUP_BATCH_ROWS: Final[int] = 64
RETENTION_CLEANUP_MAX_BATCHES: Final[int] = 32

_ENDPOINT_TIMEOUT_SECONDS: Final[float] = EndpointJsonRpcRequest(content=b'').timeout


def flight_wait_seconds(max_attempts: int) -> float:
    if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
        raise ValueError('JSON-RPC Router attempt limit must be between 1 and 10.')
    route_seconds = _ENDPOINT_TIMEOUT_SECONDS * max_attempts
    return route_seconds
