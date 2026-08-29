from dataclasses import dataclass
from typing import Protocol

import msgspec
from fastlog import log

from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import (
    JsonRpcForwardingFailure,
    JsonRpcForwardingResult,
    JsonRpcForwardingSuccess,
)
from app.model.public import JsonRpcCall, JsonRpcSuccessResponse
from app.model.system_cache import CacheLoadResult, CachePolicy
from app.model.system_jsonrpc_cache import SystemJsonRpcCacheResult
from app.services.system_cache import SystemCacheManager
from app.services.system_cache.interface import CacheStore, DistributedFlight
from app.services.system_cache.publisher import FlightReleaser, PostgresRetentionPublisher


class JsonRpcLoader(Protocol):
    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingResult | None: ...


class JsonRpcCachePolicy(Protocol):
    def classify(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> CachePolicy | None: ...


class _EvmBlockIdentity(msgspec.Struct):
    number: str | None = None


class _UtxoBlockIdentity(msgspec.Struct):
    hash: str | None = None


_STRING_DECODER = msgspec.json.Decoder(str)
_EVM_BLOCK_DECODER = msgspec.json.Decoder(_EvmBlockIdentity)
_UTXO_BLOCK_DECODER = msgspec.json.Decoder(_UtxoBlockIdentity)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Loader:
    source: JsonRpcLoader
    chain: Chain
    network: Network
    call: JsonRpcCall

    async def load(self) -> CacheLoadResult:
        routed = await self.source.load(chain=self.chain, network=self.network, call=self.call)
        if not isinstance(routed, JsonRpcForwardingSuccess) or not isinstance(routed.response, JsonRpcSuccessResponse):
            return CacheLoadResult(value=routed, payload=None)
        payload = routed.response.result
        if payload == b'null':
            return CacheLoadResult(value=payload, payload=None)
        if not _matches_identity(self.call, payload):
            log.warning(f'System JSON-RPC Cache result identity mismatch | Method:{self.call.method}')
            return CacheLoadResult(value=payload, payload=None)
        return CacheLoadResult(value=payload, payload=payload)


class SystemJsonRpcCacheManager:
    def __init__(self, core: SystemCacheManager, policies: JsonRpcCachePolicy) -> None:
        self._core = core
        self._policies = policies

    @classmethod
    def create(
        cls,
        store: CacheStore,
        policies: JsonRpcCachePolicy,
        redis_flight: DistributedFlight,
        *,
        postgres_flight: DistributedFlight | None = None,
        postgres_publisher: PostgresRetentionPublisher | None = None,
        flight_releaser: FlightReleaser | None = None,
        flight_wait_seconds: float,
    ) -> 'SystemJsonRpcCacheManager':
        core = SystemCacheManager(
            store,
            redis_flight,
            postgres_flight=postgres_flight,
            postgres_publisher=postgres_publisher,
            flight_releaser=flight_releaser,
            flight_wait_seconds=flight_wait_seconds,
        )
        return cls(core, policies)

    async def close(self, *, drain_seconds: float) -> None:
        await self._core.close(drain_seconds=drain_seconds)

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
        policy = self._policies.classify(chain=chain, network=network, call=call)
        result = await self._core.get_with_usage(
            policy=policy,
            operation=call.method,
            loader=_Loader(source=loader, chain=chain, network=network, call=call),
        )
        value = _jsonrpc_value(result.value)
        return SystemJsonRpcCacheResult(value=value, eligible=result.eligible, hit=result.hit)

    async def lookup_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
    ) -> SystemJsonRpcCacheResult:
        policy = self._policies.classify(chain=chain, network=network, call=call)
        result = await self._core.lookup_with_usage(policy=policy, operation=call.method)
        value = _jsonrpc_value(result.value)
        return SystemJsonRpcCacheResult(value=value, eligible=result.eligible, hit=result.hit)

    async def lookup_result(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> bytes | None:
        result = await self.lookup_result_with_usage(chain=chain, network=network, call=call)
        return result.value if isinstance(result.value, bytes) else None


def _jsonrpc_value(value: object | None) -> bytes | JsonRpcForwardingResult | None:
    if isinstance(value, bytes | JsonRpcForwardingSuccess | JsonRpcForwardingFailure):
        return value
    return None


def _matches_identity(call: JsonRpcCall, result: bytes) -> bool:
    try:
        if call.method == 'getblockhash':
            block_hash = _STRING_DECODER.decode(result)
            return 1 <= len(block_hash) <= 128 and block_hash.isascii()
        if call.method == 'getblock':
            if not isinstance(call.params, list) or not call.params or not isinstance(call.params[0], str):
                return False
            response_hash = _UTXO_BLOCK_DECODER.decode(result).hash
            return response_hash is not None and response_hash.lower() == call.params[0].lower()
        if call.method != 'eth_getBlockByNumber':
            return True
        if not isinstance(call.params, list) or not call.params:
            return False
        height = call.params[0]
        if not isinstance(height, str):
            return False
        identity_value = _EVM_BLOCK_DECODER.decode(result).number
        if identity_value is None or not identity_value.startswith('0x'):
            return False
        return int(identity_value[2:], 16) == int(height[2:], 16)
    except (msgspec.DecodeError, ValueError):
        return False
