from dataclasses import dataclass
from typing import Protocol

import msgspec
from fastlog import log

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointResponse
from app.model.http_api_forwarding import (
    HttpApiForwardingFailure,
    HttpApiForwardingResult,
    HttpApiForwardingSuccess,
)
from app.model.public import PublicHttpApiRequest
from app.model.system_cache import CacheLoadResult
from app.model.system_http_api_cache import SystemHttpApiCacheResult
from app.services.system_cache import SystemCacheManager
from app.services.system_http_api_cache.policy import SystemHttpApiCachePolicy, TronHttpCacheRequest


class HttpApiLoader(Protocol):
    async def load(self) -> HttpApiForwardingResult: ...


class _CachedResponse(msgspec.Struct):
    status_code: int
    headers: list[tuple[str, str]]
    body: bytes


class _NodeInfo(msgspec.Struct):
    solidity_block: str | None = msgspec.field(default=None, name='solidityBlock')


class _BlockRawData(msgspec.Struct):
    number: int | None = None


class _BlockHeader(msgspec.Struct):
    raw_data: _BlockRawData | None = None


class _Block(msgspec.Struct):
    block_header: _BlockHeader | None = None


_NODE_INFO_DECODER = msgspec.json.Decoder(_NodeInfo)
_BLOCK_DECODER = msgspec.json.Decoder(_Block)
_CACHE_DECODER = msgspec.msgpack.Decoder(_CachedResponse)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Loader:
    source: HttpApiLoader
    request: TronHttpCacheRequest

    async def load(self) -> CacheLoadResult:
        routed = await self.source.load()
        if not isinstance(routed, HttpApiForwardingSuccess):
            return CacheLoadResult(value=routed, payload=None)
        response = routed.response
        if response.status_code != 200 or not _matches_response(self.request, response.body):
            return CacheLoadResult(value=routed, payload=None)
        cached = _CachedResponse(status_code=response.status_code, headers=list(response.headers), body=response.body)
        return CacheLoadResult(value=routed, payload=msgspec.msgpack.encode(cached))


class SystemHttpApiCacheManager:
    def __init__(self, core: SystemCacheManager, policies: SystemHttpApiCachePolicy) -> None:
        self._core = core
        self._policies = policies

    async def get_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        request: PublicHttpApiRequest,
        loader: HttpApiLoader,
    ) -> SystemHttpApiCacheResult:
        classified = self._policies.classify(chain=chain, network=network, request=request)
        policy = classified.policy if classified is not None else None
        result = await self._core.get_with_usage(
            policy=policy,
            operation=request.path,
            loader=_Loader(source=loader, request=classified) if classified is not None else _UnusedLoader(),
        )
        value, hit = _http_value(result.value, hit=result.hit)
        return SystemHttpApiCacheResult(value=value, eligible=result.eligible, hit=hit)

    async def lookup_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        request: PublicHttpApiRequest,
    ) -> SystemHttpApiCacheResult:
        classified = self._policies.classify(chain=chain, network=network, request=request)
        policy = classified.policy if classified is not None else None
        result = await self._core.lookup_with_usage(policy=policy, operation=request.path)
        value, hit = _http_value(result.value, hit=result.hit)
        return SystemHttpApiCacheResult(value=value, eligible=result.eligible, hit=hit)


class _UnusedLoader:
    async def load(self) -> CacheLoadResult:
        return CacheLoadResult(value=None, payload=None)


def _http_value(value: object | None, *, hit: bool) -> tuple[HttpApiForwardingResult | None, bool]:
    if isinstance(value, HttpApiForwardingSuccess | HttpApiForwardingFailure):
        return value, hit
    if not isinstance(value, bytes):
        return None, False
    try:
        cached = _CACHE_DECODER.decode(value)
    except msgspec.DecodeError as exc:
        log.warning(f'System HTTP API Cache payload decode failed | Error:{exc!r}')
        return None, False
    response = EndpointResponse(
        status_code=cached.status_code,
        headers=tuple(cached.headers),
        body=cached.body,
        request_bytes=0,
        response_bytes=len(cached.body),
    )
    return HttpApiForwardingSuccess(response=response), hit


def _matches_response(request: TronHttpCacheRequest, body: bytes) -> bool:
    try:
        if request.expected_height is None:
            solidity_block = _NODE_INFO_DECODER.decode(body).solidity_block
            if solidity_block is None:
                return False
            height, separator, block_id = solidity_block.partition(',ID:')
            return bool(separator and block_id) and int(height.removeprefix('Num:')) >= 0
        block = _BLOCK_DECODER.decode(body)
        raw_data = block.block_header.raw_data if block.block_header is not None else None
        return raw_data is not None and raw_data.number == request.expected_height
    except (msgspec.DecodeError, ValueError):
        return False
