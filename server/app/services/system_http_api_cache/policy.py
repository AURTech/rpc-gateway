from collections.abc import Mapping
from dataclasses import dataclass

import orjson

from app.model.blockchain import Chain, Network
from app.model.public import PublicHttpApiRequest
from app.model.system_cache import CachePolicy, CacheTier
from app.model.transport import Transport
from app.services.system_cache.key import build_cache_key

_NODE_INFO = '/wallet/getnodeinfo'
_BLOCK_BY_NUMBER = '/wallet/getblockbynum'


@dataclass(frozen=True, slots=True, kw_only=True)
class TronHttpCacheRequest:
    policy: CachePolicy
    expected_height: int | None


class SystemHttpApiCachePolicy:
    def __init__(self, *, redis_ttl_ms: int, postgres_retention_seconds: Mapping[Chain, int]) -> None:
        if isinstance(redis_ttl_ms, bool) or not 10 <= redis_ttl_ms <= 60_000:
            raise ValueError('System HTTP API Cache Redis TTL must be between 10 and 60000 milliseconds.')
        if set(postgres_retention_seconds) != set(Chain):
            raise ValueError('System HTTP API Cache PostgreSQL retention must define every supported chain.')
        if any(isinstance(seconds, bool) or not 60 <= seconds <= 604_800 for seconds in postgres_retention_seconds.values()):
            raise ValueError('System HTTP API Cache PostgreSQL retention must be between 60 seconds and 7 days.')
        self._redis_ttl_ms = redis_ttl_ms
        self._postgres_retention_seconds = dict(postgres_retention_seconds)

    def classify(
        self,
        *,
        chain: Chain,
        network: Network,
        request: PublicHttpApiRequest,
    ) -> TronHttpCacheRequest | None:
        if chain is not Chain.TRON or request.method != 'POST' or request.query:
            return None
        if request.path == _NODE_INFO and request.body == b'':
            policy = CachePolicy(
                key=build_cache_key(
                    transport=Transport.HTTP_API,
                    chain=chain,
                    network=network,
                    operation=_NODE_INFO,
                    identity='solidity',
                ),
                tier=CacheTier.REDIS_TTL,
                retention_seconds=None,
                ttl_ms=self._redis_ttl_ms,
                sequence=None,
            )
            return TronHttpCacheRequest(policy=policy, expected_height=None)
        if request.path != _BLOCK_BY_NUMBER:
            return None
        height = _block_height(request.body)
        if height is None:
            return None
        policy = CachePolicy(
            key=build_cache_key(
                transport=Transport.HTTP_API,
                chain=chain,
                network=network,
                operation=_BLOCK_BY_NUMBER,
                identity={'num': height, 'visible': True},
            ),
            tier=CacheTier.POSTGRES_RETENTION,
            retention_seconds=self._postgres_retention_seconds[chain],
            ttl_ms=None,
            sequence=height,
        )
        return TronHttpCacheRequest(policy=policy, expected_height=height)


def _block_height(body: bytes) -> int | None:
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or set(payload) != {'num', 'visible'} or payload.get('visible') is not True:
        return None
    height = payload.get('num')
    if isinstance(height, bool) or not isinstance(height, int) or height < 0:
        return None
    return height
