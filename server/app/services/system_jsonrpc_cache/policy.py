from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.public import JsonRpcCall
from app.model.system_cache import CacheKey, CachePolicy, CacheTier
from app.model.transport import Transport
from app.services.system_cache.key import build_cache_key

_EVM_RETENTION_METHODS: Final[frozenset[str]] = frozenset({'eth_getBlockByNumber', 'debug_traceBlockByNumber'})
_REDIS_TTL_METHODS: Final[Mapping[Protocol, frozenset[str]]] = MappingProxyType(
    {
        Protocol.EVM: frozenset({'eth_blockNumber'}),
        Protocol.SVM: frozenset({'getSlot', 'getLatestBlockhash'}),
        Protocol.UTXO: frozenset({'getblockchaininfo'}),
        Protocol.TRON: frozenset({'eth_blockNumber'}),
    }
)


def _cache_key(*, chain: Chain, network: Network, method: str, identity: object) -> CacheKey:
    return build_cache_key(
        transport=Transport.JSONRPC,
        chain=chain,
        network=network,
        operation=method,
        identity=identity,
    )


def _hex_height(value: object) -> int | None:
    if not isinstance(value, str) or len(value) < 3 or not value.startswith('0x'):
        return None
    try:
        height = int(value[2:], 16)
    except ValueError:
        return None
    return height if height >= 0 else None


def _evm_retention_height(call: JsonRpcCall) -> int | None:
    if call.method not in _EVM_RETENTION_METHODS or not isinstance(call.params, list) or not call.params:
        return None
    height = _hex_height(call.params[0])
    if height is None:
        return None
    if call.method == 'eth_getBlockByNumber':
        return height if len(call.params) == 2 and call.params[1] is False else None
    trace_config = {'tracer': 'callTracer', 'tracerConfig': {'withLog': True}}
    return height if len(call.params) == 2 and call.params[1] == trace_config else None


def _svm_retention_slot(call: JsonRpcCall) -> int | None:
    if call.method != 'getBlock' or not isinstance(call.params, list) or not call.params:
        return None
    slot = call.params[0]
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        return None
    if len(call.params) != 2 or not isinstance(call.params[1], dict):
        return None
    config = call.params[1]
    if not set(config).issubset({'encoding', 'commitment', 'rewards', 'maxSupportedTransactionVersion'}):
        return None
    valid = (
        config.get('encoding', 'json') in {'json', 'jsonParsed'}
        and config.get('commitment', 'finalized') == 'finalized'
        and config.get('rewards', True) is False
        and config.get('maxSupportedTransactionVersion', 0) == 0
    )
    return slot if valid else None


def _is_utxo_retention(call: JsonRpcCall) -> bool:
    return (
        call.method == 'getblock'
        and isinstance(call.params, list)
        and len(call.params) == 2
        and isinstance(call.params[0], str)
        and 1 <= len(call.params[0]) <= 128
        and call.params[0].isascii()
        and call.params[1] == 3
    )


def _utxo_hash_height(call: JsonRpcCall) -> int | None:
    if call.method != 'getblockhash' or not isinstance(call.params, list) or len(call.params) != 1:
        return None
    height = call.params[0]
    if isinstance(height, bool) or not isinstance(height, int) or height < 0:
        return None
    return height


def _is_default_params(call: JsonRpcCall) -> bool:
    return call.params is None or call.params == []


def _is_finalized_svm_ttl(call: JsonRpcCall) -> bool:
    if _is_default_params(call):
        return True
    return isinstance(call.params, list) and call.params == [{'commitment': 'finalized'}]


def _uses_redis_ttl(protocol: Protocol, call: JsonRpcCall) -> bool:
    if call.method not in _REDIS_TTL_METHODS[protocol]:
        return False
    if protocol in {Protocol.EVM, Protocol.TRON, Protocol.UTXO}:
        return _is_default_params(call)
    return _is_finalized_svm_ttl(call)


class SystemJsonRpcCachePolicy:
    def __init__(self, *, redis_ttl_ms: int, postgres_retention_seconds: Mapping[Chain, int]) -> None:
        if isinstance(redis_ttl_ms, bool) or not 10 <= redis_ttl_ms <= 60_000:
            raise ValueError('System JSON-RPC Cache Redis TTL must be between 10 and 60000 milliseconds.')
        if set(postgres_retention_seconds) != set(Chain):
            raise ValueError('System JSON-RPC Cache PostgreSQL retention must define every supported chain.')
        if any(isinstance(seconds, bool) or not 60 <= seconds <= 604_800 for seconds in postgres_retention_seconds.values()):
            raise ValueError('System JSON-RPC Cache PostgreSQL retention must be between 60 seconds and 7 days.')
        self._redis_ttl_ms = redis_ttl_ms
        self._postgres_retention_seconds = dict(postgres_retention_seconds)

    def classify(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> CachePolicy | None:
        if call.is_notification:
            return None
        protocol = CHAIN_CATALOG[chain].protocol
        if _uses_redis_ttl(protocol, call):
            return CachePolicy(
                key=_cache_key(chain=chain, network=network, method=call.method, identity='finalized'),
                tier=CacheTier.REDIS_TTL,
                retention_seconds=None,
                ttl_ms=self._redis_ttl_ms,
                sequence=None,
            )
        hash_height = _utxo_hash_height(call) if protocol is Protocol.UTXO else None
        if hash_height is not None:
            retention_seconds = self._postgres_retention_seconds[chain]
            return CachePolicy(
                key=_cache_key(chain=chain, network=network, method=call.method, identity=hash_height),
                tier=CacheTier.REDIS_TTL,
                retention_seconds=None,
                ttl_ms=retention_seconds * 1000,
                sequence=hash_height,
            )
        sequence: int | None = None
        eligible = False
        if protocol is Protocol.EVM:
            sequence = _evm_retention_height(call)
            eligible = sequence is not None
        elif protocol is Protocol.SVM:
            sequence = _svm_retention_slot(call)
            eligible = sequence is not None
        elif protocol is Protocol.UTXO:
            eligible = _is_utxo_retention(call)
        if not eligible:
            return None
        identity: object = call.params
        if protocol is Protocol.EVM and sequence is not None:
            identity = [hex(sequence), call.params[1] if isinstance(call.params, list) else None]
        elif protocol is Protocol.SVM and sequence is not None and isinstance(call.params, list):
            config = call.params[1]
            if not isinstance(config, dict):
                return None
            identity = [
                sequence,
                {
                    'encoding': config.get('encoding', 'json'),
                    'commitment': 'finalized',
                    'rewards': False,
                    'maxSupportedTransactionVersion': config.get('maxSupportedTransactionVersion', 0),
                },
            ]
        elif protocol is Protocol.UTXO and isinstance(call.params, list):
            identity = [call.params[0].lower(), 3]
        retention_seconds = self._postgres_retention_seconds[chain]
        return CachePolicy(
            key=_cache_key(chain=chain, network=network, method=call.method, identity=identity),
            tier=CacheTier.POSTGRES_RETENTION,
            retention_seconds=retention_seconds,
            ttl_ms=None,
            sequence=sequence,
        )
