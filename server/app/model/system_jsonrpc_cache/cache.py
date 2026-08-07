from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import JsonRpcForwardingResult


class CacheTier(StrEnum):
    REDIS_TTL = 'redis_ttl'
    POSTGRES_RETENTION = 'postgres_retention'


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheKey:
    chain: Chain
    network: Network
    method: str
    digest: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheFlightLease:
    token: str
    fence: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CachePolicy:
    key: CacheKey
    tier: CacheTier
    retention_seconds: int | None
    ttl_ms: int | None
    sequence: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheEntry:
    key: CacheKey
    tier: CacheTier
    payload: bytes
    fresh_until: datetime | None
    stale_until: datetime | None
    sequence: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemJsonRpcCacheResult:
    value: bytes | JsonRpcForwardingResult | None
    eligible: bool
    hit: bool
