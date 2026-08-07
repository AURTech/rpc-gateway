import asyncio
import contextlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import msgspec
from fastlog import log

from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import JsonRpcForwardingResult, JsonRpcForwardingSuccess
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.model.system_jsonrpc_cache import (
    CacheEntry,
    CacheFlightLease,
    CacheKey,
    CachePolicy,
    CacheTier,
    SystemJsonRpcCacheResult,
)
from app.services.system_jsonrpc_cache.interface import (
    CachePolicyProvider,
    CacheStore,
    DistributedFlight,
    JsonRpcLoader,
)
from app.services.system_jsonrpc_cache.limits import (
    COMMIT_CANCEL_TIMEOUT_SECONDS,
    FLIGHT_HEARTBEAT_SECONDS,
    MAX_WAITERS,
    STALE_MS,
    STORE_TIMEOUT_SECONDS,
)
from app.services.system_jsonrpc_cache.publisher import FlightReleaser, PostgresRetentionPublisher


@dataclass(slots=True, kw_only=True)
class _Flight:
    event: asyncio.Event
    waiters: int = 0
    result: '_CacheLoad | None' = None


@dataclass(frozen=True, slots=True, kw_only=True)
class _CacheLoad:
    value: bytes | JsonRpcForwardingResult | None
    hit: bool
    flight_hit: bool = False


class _EvmBlockIdentity(msgspec.Struct):
    number: str | None = None


class _UtxoBlockIdentity(msgspec.Struct):
    hash: str | None = None


_STRING_DECODER = msgspec.json.Decoder(str)
_EVM_BLOCK_DECODER = msgspec.json.Decoder(_EvmBlockIdentity)
_UTXO_BLOCK_DECODER = msgspec.json.Decoder(_UtxoBlockIdentity)


class SystemJsonRpcCacheManager:
    def __init__(
        self,
        store: CacheStore,
        policies: CachePolicyProvider,
        redis_flight: DistributedFlight,
        *,
        postgres_flight: DistributedFlight | None = None,
        postgres_publisher: PostgresRetentionPublisher | None = None,
        flight_releaser: FlightReleaser | None = None,
        flight_wait_seconds: float,
    ) -> None:
        if isinstance(flight_wait_seconds, bool) or not 1 <= flight_wait_seconds <= 120:
            raise ValueError('System JSON-RPC Cache flight wait must be between 1 and 120 seconds.')
        self._store = store
        self._policies = policies
        self._redis_flight = redis_flight
        self._postgres_flight = postgres_flight if postgres_flight is not None else redis_flight
        self._postgres_publisher = postgres_publisher or PostgresRetentionPublisher(store)
        self._flight_releaser = flight_releaser or FlightReleaser()
        self._max_waiters = MAX_WAITERS
        self._stale_ms = STALE_MS
        self._flight_wait_seconds = flight_wait_seconds
        self._store_timeout_seconds = STORE_TIMEOUT_SECONDS
        self._flights: dict[CacheKey, _Flight] = {}
        self._waiters = 0

    async def close(self, *, drain_seconds: float) -> None:
        if drain_seconds < 0:
            raise ValueError('System JSON-RPC Cache drain time cannot be negative.')
        deadline = time.monotonic() + drain_seconds
        await self._postgres_publisher.close(drain_seconds=drain_seconds)
        await self._flight_releaser.close(drain_seconds=max(0.0, deadline - time.monotonic()))

    async def get_result(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
        loader: JsonRpcLoader,
    ) -> bytes | JsonRpcForwardingResult | None:
        result = await self.get_result_with_usage(chain=chain, network=network, call=call, loader=loader)
        return result.value

    async def get_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
        loader: JsonRpcLoader,
    ) -> SystemJsonRpcCacheResult:
        """Return one raw JSON result when the request is safe for system-wide reuse.

        Cache failures fail open. The request-bound loader result is returned after any executed miss
        so callers never repeat an Endpoint request merely because the result cannot be published.
        """
        policy = self._policies.classify(chain=chain, network=network, call=call)
        if policy is None:
            return SystemJsonRpcCacheResult(value=None, eligible=False, hit=False)

        flight, winner = self._join(policy.key)
        if flight is None:
            return self._result(_CacheLoad(value=None, hit=False), flight_joined=False)
        if not winner:
            loaded = await self._wait_local(flight)
            return self._result(loaded, flight_joined=True)

        loaded = _CacheLoad(value=None, hit=False)
        try:
            saved = await self._read_entry(policy, method=call.method)
            if saved is not None and self._is_fresh(saved, policy):
                loaded = _CacheLoad(value=saved.payload, hit=True, flight_hit=True)
                return self._result(loaded, flight_joined=False)
            stale = saved.payload if saved is not None and self._is_stale_usable(saved, policy) else None
            saved_payload = saved.payload if saved is not None else None
            loaded = await self._load(
                policy,
                call=call,
                chain=chain,
                network=network,
                loader=loader,
                stale=stale,
                saved_payload=saved_payload,
            )
            return self._result(loaded, flight_joined=False)
        except Exception as exc:
            log.warning(f'System JSON-RPC Cache load failed | Method:{call.method} | Error:{exc!r}')
            return self._result(_CacheLoad(value=None, hit=False), flight_joined=False)
        finally:
            flight.result = loaded
            self._flights.pop(policy.key, None)
            flight.event.set()

    async def lookup_result(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> bytes | None:
        result = await self.lookup_result_with_usage(chain=chain, network=network, call=call)
        return result.value if isinstance(result.value, bytes) else None

    async def lookup_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
    ) -> SystemJsonRpcCacheResult:
        """Read an existing reusable result without invoking a request-bound loader."""
        policy = self._policies.classify(chain=chain, network=network, call=call)
        if policy is None:
            return SystemJsonRpcCacheResult(value=None, eligible=False, hit=False)
        saved = await self._read_entry(policy, method=call.method)
        if saved is None or not (self._is_fresh(saved, policy) or self._is_stale_usable(saved, policy)):
            return self._result(_CacheLoad(value=None, hit=False), flight_joined=False)
        return self._result(_CacheLoad(value=saved.payload, hit=True, flight_hit=True), flight_joined=False)

    def _result(self, loaded: _CacheLoad, *, flight_joined: bool) -> SystemJsonRpcCacheResult:
        hit = loaded.flight_hit if flight_joined else loaded.hit
        return SystemJsonRpcCacheResult(value=loaded.value, eligible=True, hit=hit)

    async def _read_entry(self, policy: CachePolicy, *, method: str) -> CacheEntry | None:
        try:
            async with asyncio.timeout(self._store_timeout_seconds):
                return await self._store.get(policy)
        except Exception as exc:
            log.warning(f'System JSON-RPC Cache read failed | Method:{method} | Error:{exc!r}')
            return None

    async def _load(
        self,
        policy: CachePolicy,
        *,
        call: JsonRpcCall,
        chain: Chain,
        network: Network,
        loader: JsonRpcLoader,
        stale: bytes | None,
        saved_payload: bytes | None,
    ) -> _CacheLoad:
        deadline = time.monotonic() + self._flight_wait_seconds
        distributed_flight = self._flight(policy)
        token = await distributed_flight.acquire(policy.key)
        while token is None:
            if stale is not None:
                return _CacheLoad(value=stale, hit=True, flight_hit=True)
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                return _CacheLoad(value=None, hit=False)
            released = await distributed_flight.wait(policy.key, timeout_seconds=remaining_seconds)
            if not released:
                return _CacheLoad(value=None, hit=False)
            async with asyncio.timeout(self._store_timeout_seconds):
                saved = await self._store.get(policy)
            if saved is not None and (self._is_fresh(saved, policy) or self._is_stale_usable(saved, policy)):
                return _CacheLoad(value=saved.payload, hit=True, flight_hit=True)
            token = await distributed_flight.acquire(policy.key)

        ownership_lost = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(distributed_flight, policy.key, token, ownership_lost))
        publisher_owns_lease = False
        try:
            try:
                async with asyncio.timeout(self._store_timeout_seconds):
                    saved_after_acquire = await self._store.get(policy)
                if saved_after_acquire is not None and self._is_fresh(saved_after_acquire, policy):
                    return _CacheLoad(value=saved_after_acquire.payload, hit=True, flight_hit=True)
            except Exception as exc:
                log.warning(f'System JSON-RPC Cache locked read failed | Method:{call.method} | Error:{exc!r}')
            routed = await loader.load(chain=chain, network=network, call=call)
            if not isinstance(routed, JsonRpcForwardingSuccess) or not isinstance(routed.response, JsonRpcSuccessResponse):
                value = stale if stale is not None else routed
                return _CacheLoad(value=value, hit=stale is not None, flight_hit=stale is not None)
            payload = routed.response.result
            if payload == b'null':
                return _CacheLoad(value=payload, hit=False)
            if not self._matches_identity(policy, call, payload):
                log.warning(f'System JSON-RPC Cache result identity mismatch | Method:{call.method}')
                return _CacheLoad(value=payload, hit=False)
            # TODO(security): Move cache capacity admission into a trust-aware security module.
            entry = self._entry(policy, payload)
            try:
                refresh = saved_payload is not None and saved_payload == payload and policy.tier is CacheTier.POSTGRES_RETENTION
                if policy.tier is CacheTier.POSTGRES_RETENTION:
                    publisher_owns_lease = self._postgres_publisher.submit(
                        entry,
                        token,
                        refresh=refresh,
                        flight=distributed_flight,
                        heartbeat=heartbeat,
                        ownership_lost=ownership_lost,
                    )
                    return _CacheLoad(value=payload, hit=False, flight_hit=True)
                owned = await distributed_flight.renew(policy.key, token)
                if not owned:
                    return _CacheLoad(value=payload, hit=False, flight_hit=True)
                if ownership_lost.is_set():
                    return _CacheLoad(value=payload, hit=False, flight_hit=True)
                applied = await self._commit_owned(entry, token, refresh=refresh, ownership_lost=ownership_lost)
                if applied is None:
                    return _CacheLoad(value=payload, hit=False, flight_hit=True)
                if not applied:
                    log.warning(f'System JSON-RPC Cache fenced write rejected | Method:{call.method}')
            except Exception as exc:
                log.warning(f'System JSON-RPC Cache write failed | Method:{call.method} | Error:{exc!r}')
            return _CacheLoad(value=payload, hit=False, flight_hit=True)
        finally:
            if not publisher_owns_lease:
                release_submitted = self._flight_releaser.submit(
                    flight=distributed_flight,
                    key=policy.key,
                    lease=token,
                    heartbeat=heartbeat,
                )
                if not release_submitted:
                    heartbeat.cancel()

    async def _heartbeat(
        self,
        distributed_flight: DistributedFlight,
        key: CacheKey,
        token: CacheFlightLease,
        ownership_lost: asyncio.Event,
    ) -> None:
        while True:
            await asyncio.sleep(FLIGHT_HEARTBEAT_SECONDS)
            try:
                owned = await distributed_flight.renew(key, token)
            except Exception as exc:
                log.warning(f'System JSON-RPC Cache flight heartbeat failed | Method:{key.method} | Error:{exc!r}')
                ownership_lost.set()
                return
            if not owned:
                ownership_lost.set()
                return

    async def _commit_owned(
        self,
        entry: CacheEntry,
        lease: CacheFlightLease,
        *,
        refresh: bool,
        ownership_lost: asyncio.Event,
    ) -> bool | None:
        """Cancel a store commit when the heartbeat observes that its lease was lost."""
        commit_task = asyncio.create_task(self._store.commit(entry, lease, refresh=refresh))
        lost_task = asyncio.create_task(ownership_lost.wait())
        try:
            async with asyncio.timeout(self._store_timeout_seconds):
                done, _pending = await asyncio.wait((commit_task, lost_task), return_when=asyncio.FIRST_COMPLETED)
                if commit_task in done:
                    return commit_task.result()
                return None
        finally:
            tasks = (commit_task, lost_task)
            for task in tasks:
                if not task.done():
                    task.cancel()
            _done, pending = await asyncio.wait(tasks, timeout=COMMIT_CANCEL_TIMEOUT_SECONDS)
            for task in tasks:
                if task.done():
                    self._consume_task(task)
                else:
                    task.add_done_callback(self._consume_task)
            if pending:
                log.warning(f'System JSON-RPC Cache commit cancellation exceeded deadline | Method:{entry.key.method}')

    def _flight(self, policy: CachePolicy) -> DistributedFlight:
        if policy.tier is CacheTier.POSTGRES_RETENTION:
            return self._postgres_flight
        return self._redis_flight

    @staticmethod
    def _consume_task(task: asyncio.Task[bool]) -> None:
        if task.cancelled():
            return
        with contextlib.suppress(Exception):
            task.exception()

    def _entry(self, policy: CachePolicy, payload: bytes) -> CacheEntry:
        if policy.ttl_ms is None:
            return CacheEntry(
                key=policy.key,
                tier=policy.tier,
                payload=payload,
                fresh_until=None,
                stale_until=None,
                sequence=policy.sequence,
            )
        now = datetime.now(UTC)
        fresh_until = now + timedelta(milliseconds=policy.ttl_ms)
        return CacheEntry(
            key=policy.key,
            tier=policy.tier,
            payload=payload,
            fresh_until=fresh_until,
            stale_until=fresh_until + timedelta(milliseconds=self._stale_ms),
            sequence=policy.sequence,
        )

    def _join(self, key: CacheKey) -> tuple[_Flight | None, bool]:
        flight = self._flights.get(key)
        if flight is not None:
            if self._waiters >= self._max_waiters:
                return None, False
            flight.waiters += 1
            self._waiters += 1
            return flight, False
        flight = _Flight(event=asyncio.Event())
        self._flights[key] = flight
        return flight, True

    async def _wait_local(self, flight: _Flight) -> _CacheLoad:
        try:
            await flight.event.wait()
            return flight.result or _CacheLoad(value=None, hit=False)
        finally:
            flight.waiters -= 1
            self._waiters -= 1

    @staticmethod
    def _is_fresh(entry: CacheEntry, policy: CachePolicy) -> bool:
        if policy.ttl_ms is not None and entry.fresh_until is None:
            return False
        return entry.fresh_until is None or entry.fresh_until > datetime.now(UTC)

    @staticmethod
    def _is_stale_usable(entry: CacheEntry, policy: CachePolicy) -> bool:
        if policy.ttl_ms is not None and entry.stale_until is None:
            return False
        return entry.stale_until is not None and entry.stale_until > datetime.now(UTC)

    @staticmethod
    def _matches_identity(policy: CachePolicy, call: JsonRpcCall, result: bytes) -> bool:
        try:
            if call.method == 'getblockhash':
                block_hash = _STRING_DECODER.decode(result)
                return 1 <= len(block_hash) <= 128 and block_hash.isascii()
            if call.method == 'getblock':
                if not isinstance(call.params, list) or not call.params or not isinstance(call.params[0], str):
                    return False
                response_hash = _UTXO_BLOCK_DECODER.decode(result).hash
                return response_hash is not None and response_hash.lower() == call.params[0].lower()
            if call.method != 'eth_getBlockByNumber' or policy.sequence is None:
                return True
            identity_value = _EVM_BLOCK_DECODER.decode(result).number
            if identity_value is None or not identity_value.startswith('0x'):
                return False
            return int(identity_value[2:], 16) == policy.sequence
        except (msgspec.DecodeError, ValueError):
            return False
