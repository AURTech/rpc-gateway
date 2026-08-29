import hashlib

import orjson

from app.model.blockchain import Chain, Network
from app.model.system_cache import CacheKey
from app.model.transport import Transport


def build_cache_key(
    *,
    transport: Transport,
    chain: Chain,
    network: Network,
    operation: str,
    identity: object,
) -> CacheKey:
    digest = build_cache_digest(operation=operation, identity=identity)
    return CacheKey(
        transport=transport,
        chain=chain,
        network=network,
        operation=operation,
        digest=digest,
    )


def build_cache_digest(*, operation: str, identity: object) -> str:
    canonical = orjson.dumps(
        {'operation': operation, 'identity': identity},
        option=orjson.OPT_SORT_KEYS,
    )
    return hashlib.blake2b(canonical, digest_size=20).hexdigest()
