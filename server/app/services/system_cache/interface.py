from dataclasses import dataclass
from typing import Protocol

from app.model.blockchain import Chain
from app.model.system_cache import CacheEntry, CacheFlightLease, CacheKey, CacheLoadResult, CachePolicy


@dataclass(frozen=True, slots=True, kw_only=True)
class RetentionDeleteResult:
    deleted_rows: int
    deleted_bytes: int
    has_more: bool


class CacheStore(Protocol):
    async def get(self, policy: CachePolicy) -> CacheEntry | None: ...

    async def commit(self, entry: CacheEntry, lease: CacheFlightLease, *, refresh: bool) -> bool: ...


class CacheLoader(Protocol):
    async def load(self) -> CacheLoadResult: ...


class DistributedFlight(Protocol):
    async def acquire(self, key: CacheKey) -> CacheFlightLease | None: ...

    async def renew(self, key: CacheKey, lease: CacheFlightLease) -> bool: ...

    async def release(self, key: CacheKey, lease: CacheFlightLease) -> None: ...

    async def wait(self, key: CacheKey, *, timeout_seconds: float) -> bool: ...


class RetentionStore(Protocol):
    async def delete_expired(
        self,
        chain: Chain,
        retention_seconds: int,
        *,
        max_rows: int,
        max_bytes: int,
    ) -> RetentionDeleteResult: ...
