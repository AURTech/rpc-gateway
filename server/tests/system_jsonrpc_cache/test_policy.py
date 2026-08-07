from app.model.blockchain import Chain, Network
from app.model.public import JsonRpcCall
from app.model.system_jsonrpc_cache import CacheTier
from app.services.system_jsonrpc_cache.policy import SystemJsonRpcCachePolicy


def _policy() -> SystemJsonRpcCachePolicy:
    return SystemJsonRpcCachePolicy(
        redis_ttl_ms=250,
        postgres_retention_seconds=dict.fromkeys(Chain, 3600),
    )


def test_evm_block_uses_postgres_retention_tier() -> None:
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='eth_getBlockByNumber', params=['0x64', False])

    policy = _policy().classify(chain=Chain.ETHEREUM, network=Network.MAINNET, call=call)

    assert policy is not None
    assert policy.tier is CacheTier.POSTGRES_RETENTION
    assert policy.retention_seconds == 3600
    assert policy.ttl_ms is None
    assert policy.sequence == 100


def test_utxo_hash_uses_redis_ttl_tier() -> None:
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblockhash', params=[100])

    policy = _policy().classify(chain=Chain.BITCOIN, network=Network.MAINNET, call=call)

    assert policy is not None
    assert policy.tier is CacheTier.REDIS_TTL
    assert policy.retention_seconds is None
    assert policy.ttl_ms == 3_600_000
    assert policy.sequence == 100


def test_utxo_block_uses_postgres_retention_without_height_mapping() -> None:
    block_hash = 'a' * 64
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblock', params=[block_hash, 3])

    policy = _policy().classify(chain=Chain.BITCOIN, network=Network.MAINNET, call=call)

    assert policy is not None
    assert policy.tier is CacheTier.POSTGRES_RETENTION
    assert policy.retention_seconds == 3600
    assert policy.ttl_ms is None
    assert policy.sequence is None


def test_utxo_postgres_retention_rejects_invalid_hash() -> None:
    call = JsonRpcCall(jsonrpc='2.0', id=1, method='getblock', params=['a' * 129, 3])

    policy = _policy().classify(chain=Chain.BITCOIN, network=Network.MAINNET, call=call)

    assert policy is None
