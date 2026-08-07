import asyncio
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from app.model.blockchain import Chain, Network
from app.model.runtime_state.chain.tip import ChainTip
from app.model.runtime_state.endpoint.tip import TipObservation
from app.model.runtime_state.tip import Finality, TipUnit, validate_tip_dimension
from app.services.runtime_state.chain.tip.store import ChainTipLease, ChainTipStore, RedisClock

TIP_FRESH_SECONDS: Final[int] = 60
MIN_TIP_SOURCES: Final[int] = 3
MAX_TIP_SOURCES: Final[int] = 10_000
LOCAL_CACHE_ITEMS: Final[int] = 128
LOCAL_CACHE_SECONDS: Final[float] = 0.1
SHARED_REFRESH_SECONDS: Final[int] = 1
MAX_FUTURE_SECONDS: Final[int] = 5
LEASE_CHECK_SOURCES: Final[int] = 256
DEFAULT_RECOMPUTES: Final[int] = 2
MAX_RECOMPUTES: Final[int] = 4
RECOMPUTE_WAIT_SECONDS: Final[float] = 0.1
FLIGHT_WAIT_SECONDS: Final[float] = 1.0
FLIGHT_REUSE_SECONDS: Final[float] = 0.1

type ChainTipKey = tuple[Chain, Network, TipUnit, Finality]


class TipReader(Protocol):
    def iterate(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> AsyncIterator[TipObservation]: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class _CachedTip:
    tip: ChainTip
    expires_at: float


@dataclass(frozen=True, slots=True, kw_only=True)
class _SourceTip:
    value: int
    version: int
    observed_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class _ComputedTip:
    tip: ChainTip | None
    clock: RedisClock


@dataclass(slots=True, kw_only=True)
class _Flight:
    event: asyncio.Event
    done: bool = False
    result: ChainTip | None = None
    error: Exception | None = None
    expires_at: float = 0.0


class ChainTipManager:
    def __init__(
        self,
        reader: TipReader,
        store: ChainTipStore,
        *,
        recompute_limit: int = DEFAULT_RECOMPUTES,
    ) -> None:
        if isinstance(recompute_limit, bool) or not 1 <= recompute_limit <= MAX_RECOMPUTES:
            raise ValueError('Chain tip recompute limit must be between 1 and 4.')
        self._reader = reader
        self._store = store
        self._cache: OrderedDict[ChainTipKey, _CachedTip] = OrderedDict()
        self._flights: dict[ChainTipKey, _Flight] = {}
        self._slots = asyncio.Semaphore(recompute_limit)

    async def get_tip(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> ChainTip | None:
        """Share one bounded computation per dimension without creating background work."""
        validate_tip_dimension(chain=chain, network=network, unit=unit, finality=finality)
        key = (chain, network, unit, finality)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        flight, is_winner = self._join_flight(key)
        if not is_winner:
            return await self._wait_flight(key, flight)

        result: ChainTip | None = None
        error: Exception | None = None
        reusable = False
        try:
            result = await self._load_tip(
                key=key,
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
            )
            reusable = True
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            self._finish_flight(key, flight, result=result, error=error, reusable=reusable)

    async def _load_tip(
        self,
        *,
        key: ChainTipKey,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> ChainTip | None:
        """Read or compute one dimension while preserving the distributed lease boundary."""

        saved = await self._store.get(chain=chain, network=network, unit=unit, finality=finality)
        snapshot = saved.tip
        if (
            snapshot is not None
            and self._is_fresh(snapshot, now=saved.clock.now)
            and self._cache_tip(key, snapshot, clock=saved.clock)
        ):
            return snapshot

        async with self._hold_slot() as acquired:
            if not acquired:
                return self._cache_saved(key, snapshot, clock=saved.clock)
            async with self._store.lock(
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
            ) as lease:
                if lease is None:
                    return await self._read_after_losing(
                        snapshot,
                        clock=saved.clock,
                        chain=chain,
                        network=network,
                        unit=unit,
                        finality=finality,
                    )
                result = await self._compute(
                    lease=lease,
                    chain=chain,
                    network=network,
                    unit=unit,
                    finality=finality,
                )
                if result is None:
                    return await self._read_latest(chain=chain, network=network, unit=unit, finality=finality)
                if result.tip is None:
                    if (
                        self._is_valid(snapshot, now=result.clock.now)
                        and snapshot is not None
                        and self._cache_tip(key, snapshot, clock=result.clock)
                    ):
                        return snapshot
                    return None
                saved_result = await self._store.put(result.tip, lease=lease)
                if (
                    saved_result.applied
                    and saved_result.clock is not None
                    and self._cache_tip(key, result.tip, clock=saved_result.clock)
                ):
                    return result.tip
                latest = await self._read_latest(
                    chain=chain,
                    network=network,
                    unit=unit,
                    finality=finality,
                )
                if latest is not None:
                    return latest
                return None

    def _join_flight(self, key: ChainTipKey) -> tuple[_Flight, bool]:
        """Join a finite validated dimension or become its caller-owned winner."""
        flight = self._flights.get(key)
        if flight is not None:
            if not flight.done or flight.expires_at > time.monotonic():
                return flight, False
            self._flights.pop(key, None)
        flight = _Flight(event=asyncio.Event())
        self._flights[key] = flight
        return flight, True

    async def _wait_flight(self, key: ChainTipKey, flight: _Flight) -> ChainTip | None:
        """Wait without transferring loser cancellation to the caller-owned winner."""
        if not flight.done:
            try:
                async with asyncio.timeout(FLIGHT_WAIT_SECONDS):
                    await flight.event.wait()
            except TimeoutError:
                return self._get_cached(key)
        if flight.error is not None:
            raise flight.error
        if flight.done and flight.expires_at > time.monotonic():
            return flight.result
        return self._get_cached(key)

    def _finish_flight(
        self,
        key: ChainTipKey,
        flight: _Flight,
        *,
        result: ChainTip | None,
        error: Exception | None,
        reusable: bool,
    ) -> None:
        flight.result = result
        flight.error = error
        flight.done = True
        if reusable:
            expires_at = time.monotonic() + FLIGHT_REUSE_SECONDS
            if result is not None:
                cached = self._cache.get(key)
                expires_at = min(expires_at, cached.expires_at) if cached is not None else 0.0
            flight.expires_at = expires_at
        flight.event.set()

    @asynccontextmanager
    async def _hold_slot(self) -> AsyncIterator[bool]:
        acquired = False
        try:
            try:
                async with asyncio.timeout(RECOMPUTE_WAIT_SECONDS):
                    await self._slots.acquire()
                acquired = True
            except TimeoutError:
                pass
            yield acquired
        finally:
            if acquired:
                self._slots.release()

    async def _read_latest(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> ChainTip | None:
        key = (chain, network, unit, finality)
        saved = await self._store.get(chain=chain, network=network, unit=unit, finality=finality)
        if (
            self._is_valid(saved.tip, now=saved.clock.now)
            and saved.tip is not None
            and self._cache_tip(key, saved.tip, clock=saved.clock)
        ):
            return saved.tip
        return None

    async def _read_after_losing(
        self,
        snapshot: ChainTip | None,
        *,
        clock: RedisClock,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> ChainTip | None:
        key = (chain, network, unit, finality)
        saved = self._cache_saved(key, snapshot, clock=clock)
        if saved is not None:
            return saved
        return await self._read_latest(
            chain=chain,
            network=network,
            unit=unit,
            finality=finality,
        )

    def _cache_saved(self, key: ChainTipKey, tip: ChainTip | None, *, clock: RedisClock) -> ChainTip | None:
        if self._is_valid(tip, now=clock.now) and tip is not None and self._cache_tip(key, tip, clock=clock):
            return tip
        return None

    @staticmethod
    def _is_newer(tip: TipObservation, saved: _SourceTip) -> bool:
        return tip.endpoint_version > saved.version or (
            tip.endpoint_version == saved.version and tip.observed_at > saved.observed_at
        )

    async def _compute(
        self,
        *,
        lease: ChainTipLease,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> _ComputedTip | None:
        """Aggregate at most one newest revision per Endpoint within fixed memory bounds."""
        clock = lease.clock
        renew_at = clock.anchor + lease.renew_after_seconds
        sources: dict[str, _SourceTip] = {}
        scanned = 0
        async for tip in self._reader.iterate(chain=chain, network=network, unit=unit, finality=finality):
            scanned += 1
            if scanned > MAX_TIP_SOURCES:
                clock = await self._store.renew(lease)
                return None if clock is None else _ComputedTip(tip=None, clock=clock)
            saved = sources.get(tip.endpoint_id)
            if saved is None:
                if len(sources) >= MAX_TIP_SOURCES:
                    return None
                sources[tip.endpoint_id] = _SourceTip(
                    value=tip.value,
                    version=tip.endpoint_version,
                    observed_at=tip.observed_at,
                )
            elif self._is_newer(tip, saved):
                sources[tip.endpoint_id] = _SourceTip(
                    value=tip.value,
                    version=tip.endpoint_version,
                    observed_at=tip.observed_at,
                )
            if scanned % LEASE_CHECK_SOURCES == 0 and time.monotonic() >= renew_at:
                clock = await self._store.renew(lease)
                if clock is None:
                    return None
                renew_at = clock.anchor + lease.renew_after_seconds

        clock = await self._store.renew(lease)
        if clock is None:
            return None
        fresh_after = clock.now - timedelta(seconds=TIP_FRESH_SECONDS)
        future_after = clock.now + timedelta(seconds=MAX_FUTURE_SECONDS)

        values: list[int] = []
        oldest: datetime | None = None
        newest: datetime | None = None
        for source in sources.values():
            if source.observed_at < fresh_after or source.observed_at > future_after:
                continue
            values.append(source.value)
            oldest = source.observed_at if oldest is None else min(oldest, source.observed_at)
            newest = source.observed_at if newest is None else max(newest, source.observed_at)
        sources.clear()

        if len(values) < MIN_TIP_SOURCES or oldest is None or newest is None:
            return _ComputedTip(tip=None, clock=clock)
        computed_at = clock.now
        source_valid_until = oldest + timedelta(seconds=TIP_FRESH_SECONDS)
        maximum_valid_until = computed_at + timedelta(seconds=TIP_FRESH_SECONDS)
        valid_until = min(source_valid_until, maximum_valid_until)
        if valid_until <= computed_at:
            return _ComputedTip(tip=None, clock=clock)
        values.sort()
        value = values[(len(values) - 1) // 2]
        return _ComputedTip(
            tip=ChainTip(
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
                value=value,
                source_count=len(values),
                observed_at=newest,
                computed_at=computed_at,
                valid_until=valid_until,
            ),
            clock=clock,
        )

    def _get_cached(self, key: ChainTipKey) -> ChainTip | None:
        cached = self._cache.get(key)
        if cached is None:
            return None
        if cached.expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return cached.tip

    def _cache_tip(self, key: ChainTipKey, tip: ChainTip, *, clock: RedisClock) -> bool:
        hard_seconds = (tip.valid_until - clock.now).total_seconds()
        expires_at = clock.anchor + min(LOCAL_CACHE_SECONDS, hard_seconds)
        if expires_at <= time.monotonic():
            return False
        self._cache[key] = _CachedTip(tip=tip, expires_at=expires_at)
        self._cache.move_to_end(key)
        while len(self._cache) > LOCAL_CACHE_ITEMS:
            self._cache.popitem(last=False)
        return True

    @staticmethod
    def _is_valid(tip: ChainTip | None, *, now: datetime) -> bool:
        return tip is not None and tip.valid_until > now

    @classmethod
    def _is_fresh(cls, tip: ChainTip | None, *, now: datetime) -> bool:
        return (
            cls._is_valid(tip, now=now)
            and tip is not None
            and tip.computed_at + timedelta(seconds=SHARED_REFRESH_SECONDS) > now
        )
