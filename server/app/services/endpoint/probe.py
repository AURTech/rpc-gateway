import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Final, TypeIs

import orjson

from app.clients.endpoint import EndpointHttpClient
from app.clients.transport import (
    HttpTransportConfigError,
    HttpTransportConnectionError,
    HttpTransportError,
    HttpTransportResponse,
    HttpTransportResponseError,
    HttpTransportTimeoutError,
)
from app.infra.outbound_policy import HTTP_OUTBOUND_SCHEMES, OutboundTargetError, OutboundTargetPolicy
from app.model.blockchain import CHAIN_CATALOG, Chain, Protocol
from app.model.endpoint import EndpointProtocol
from app.model.runtime_state.endpoint.health import HealthFailure
from app.orm.endpoint import Endpoint
from app.services.endpoint.crypto import EndpointSecretConfigError
from app.services.endpoint.transport import build_endpoint_connection

_JSONRPC_REQUEST_ID: Final[int] = 1
_LIMIT_MESSAGE_PARTS: Final[tuple[str, ...]] = (
    'rate limit',
    'rate-limit',
    'too many request',
    'quota exceeded',
    'request limit exceeded',
)
_AUTH_MESSAGE_PARTS: Final[tuple[str, ...]] = (
    'unauthorized',
    'forbidden',
    'authentication failed',
    'invalid api key',
    'invalid token',
    'api key is invalid',
    'api key is missing',
)


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointProbeResult:
    checked_at: datetime
    success: bool
    limited: bool
    latency_ms: float | None
    failure: HealthFailure | None


def _failed_probe(failure: HealthFailure, *, latency_ms: float | None = None) -> EndpointProbeResult:
    return EndpointProbeResult(
        checked_at=datetime.now(UTC),
        success=False,
        limited=False,
        latency_ms=latency_ms,
        failure=failure,
    )


def _latency_ms(started: float) -> float:
    return max(0.0, (perf_counter() - started) * 1000)


def _jsonrpc_request(protocol: Protocol) -> bytes:
    if protocol in {Protocol.EVM, Protocol.TRON}:
        method = 'eth_blockNumber'
        params: list[object] = []
    elif protocol is Protocol.SVM:
        method = 'getSlot'
        params = [{'commitment': 'finalized'}]
    elif protocol is Protocol.UTXO:
        method = 'getblockchaininfo'
        params = []
    else:
        raise ValueError('Endpoint chain protocol is unsupported.')
    return orjson.dumps(
        {
            'jsonrpc': '2.0',
            'id': _JSONRPC_REQUEST_ID,
            'method': method,
            'params': params,
        }
    )


def _is_integer(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_hex_quantity(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith('0x') or len(value) < 3:
        return False
    digits = value[2:]
    if len(digits) > 1 and digits[0] == '0':
        return False
    return all(character in '0123456789abcdefABCDEF' for character in digits)


def _valid_jsonrpc_result(protocol: Protocol, result: object) -> bool:
    if protocol in {Protocol.EVM, Protocol.TRON}:
        return _valid_hex_quantity(result)
    if protocol is Protocol.SVM:
        return _is_integer(result) and result >= 0
    if protocol is not Protocol.UTXO or not isinstance(result, dict):
        return False
    blocks = result.get('blocks')
    headers = result.get('headers')
    initial_download = result.get('initialblockdownload')
    return (
        _is_integer(blocks)
        and blocks >= 0
        and _is_integer(headers)
        and headers >= 0
        and (initial_download is None or isinstance(initial_download, bool))
    )


def _jsonrpc_limit_error(code: int, message: str) -> bool:
    normalized = message.casefold()
    return code == 429 or any(part in normalized for part in _LIMIT_MESSAGE_PARTS)


def _validate_jsonrpc(body: bytes, protocol: Protocol) -> tuple[bool, bool, HealthFailure | None]:
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError:
        return False, False, HealthFailure.PROTOCOL
    if not isinstance(payload, dict):
        return False, False, HealthFailure.PROTOCOL
    version = payload.get('jsonrpc')
    if protocol is Protocol.UTXO:
        if version not in {None, '2.0'}:
            return False, False, HealthFailure.PROTOCOL
    elif version != '2.0':
        return False, False, HealthFailure.PROTOCOL
    response_id = payload.get('id')
    if not _is_integer(response_id) or response_id != _JSONRPC_REQUEST_ID:
        return False, False, HealthFailure.PROTOCOL
    error = payload.get('error')
    has_error = error is not None
    result = payload.get('result')
    has_result = 'result' in payload and result is not None
    if has_error == has_result:
        return False, False, HealthFailure.PROTOCOL
    if has_error:
        if not isinstance(error, dict):
            return False, False, HealthFailure.PROTOCOL
        code = error.get('code')
        message = error.get('message')
        if not _is_integer(code) or not isinstance(message, str):
            return False, False, HealthFailure.PROTOCOL
        if _jsonrpc_limit_error(code, message):
            return True, True, None
        normalized = message.casefold()
        if any(part in normalized for part in _AUTH_MESSAGE_PARTS):
            return False, False, HealthFailure.AUTH
        return True, False, None
    if not _valid_jsonrpc_result(protocol, result):
        return False, False, HealthFailure.PROTOCOL
    return True, False, None


def _validate_tron_http_api(body: bytes) -> bool:
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    block_header = payload.get('block_header')
    if not isinstance(block_header, dict):
        return False
    raw_data = block_header.get('raw_data')
    if not isinstance(raw_data, dict):
        return False
    number = raw_data.get('number')
    return _is_integer(number) and number >= 0


def _classify_http_status(response: HttpTransportResponse, protocol: Protocol) -> tuple[bool, bool, HealthFailure | None]:
    status_code = response.status_code
    if status_code == 429:
        return True, True, None
    if status_code in {401, 403}:
        return False, False, HealthFailure.AUTH
    if status_code >= 500:
        return False, False, HealthFailure.SERVER
    if status_code < 200 or status_code >= 300:
        return False, False, HealthFailure.PROTOCOL
    return _validate_jsonrpc(response.body, protocol)


def _classify_http_api(response: HttpTransportResponse) -> tuple[bool, bool, HealthFailure | None]:
    status_code = response.status_code
    if status_code == 429:
        return True, True, None
    if status_code in {401, 403}:
        return False, False, HealthFailure.AUTH
    if status_code >= 500:
        return False, False, HealthFailure.SERVER
    if status_code < 200 or status_code >= 300:
        return False, False, HealthFailure.PROTOCOL
    return (True, False, None) if _validate_tron_http_api(response.body) else (False, False, HealthFailure.PROTOCOL)


class EndpointProbeManager:
    def __init__(
        self,
        *,
        http_client: EndpointHttpClient,
        target_policy: OutboundTargetPolicy,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> None:
        self._http_client = http_client
        self._target_policy = target_policy
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def probe(self, endpoint: Endpoint) -> EndpointProbeResult:
        """Execute the fixed request for one stored Endpoint, including disabled entries."""
        try:
            chain = Chain(endpoint.chain)
            protocol = CHAIN_CATALOG[chain].protocol
            transport = EndpointProtocol(endpoint.protocol)
            if transport is EndpointProtocol.JSONRPC:
                return await self._probe_jsonrpc(endpoint, protocol)
            if transport is EndpointProtocol.HTTP_API and protocol is Protocol.TRON:
                return await self._probe_http_api(endpoint)
            return _failed_probe(HealthFailure.CONFIG)
        except (EndpointSecretConfigError, HttpTransportConfigError, ValueError):
            return _failed_probe(HealthFailure.CONFIG)

    async def _probe_jsonrpc(self, endpoint: Endpoint, protocol: Protocol) -> EndpointProbeResult:
        connection = build_endpoint_connection(endpoint)
        try:
            self._target_policy.parse_url(connection.url, allowed_schemes=HTTP_OUTBOUND_SCHEMES)
        except OutboundTargetError:
            return _failed_probe(HealthFailure.CONFIG)
        content = _jsonrpc_request(protocol)
        started = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._http_client.request_jsonrpc(
                    connection,
                    content,
                    timeout=self._timeout_seconds,
                    max_response_bytes=self._max_response_bytes,
                )
        except TimeoutError:
            return _failed_probe(HealthFailure.TIMEOUT, latency_ms=_latency_ms(started))
        except HttpTransportTimeoutError:
            return _failed_probe(HealthFailure.TIMEOUT, latency_ms=_latency_ms(started))
        except HttpTransportConnectionError:
            return _failed_probe(HealthFailure.CONNECTION, latency_ms=_latency_ms(started))
        except HttpTransportResponseError:
            return _failed_probe(HealthFailure.PROTOCOL, latency_ms=_latency_ms(started))
        except HttpTransportError:
            return _failed_probe(HealthFailure.CONNECTION, latency_ms=_latency_ms(started))
        latency_ms = _latency_ms(started)
        success, limited, failure = _classify_http_status(response, protocol)
        return EndpointProbeResult(
            checked_at=datetime.now(UTC),
            success=success,
            limited=limited,
            latency_ms=latency_ms,
            failure=failure,
        )

    async def _probe_http_api(self, endpoint: Endpoint) -> EndpointProbeResult:
        connection = build_endpoint_connection(endpoint)
        try:
            self._target_policy.parse_url(connection.url, allowed_schemes=HTTP_OUTBOUND_SCHEMES)
        except OutboundTargetError:
            return _failed_probe(HealthFailure.CONFIG)
        started = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._http_client.request_http_api(
                    connection,
                    'POST',
                    'wallet/getnowblock',
                    headers={'Content-Type': 'application/json'},
                    content=b'{}',
                    timeout=self._timeout_seconds,
                    max_response_bytes=self._max_response_bytes,
                )
        except TimeoutError:
            return _failed_probe(HealthFailure.TIMEOUT, latency_ms=_latency_ms(started))
        except HttpTransportTimeoutError:
            return _failed_probe(HealthFailure.TIMEOUT, latency_ms=_latency_ms(started))
        except HttpTransportConnectionError:
            return _failed_probe(HealthFailure.CONNECTION, latency_ms=_latency_ms(started))
        except HttpTransportResponseError:
            return _failed_probe(HealthFailure.PROTOCOL, latency_ms=_latency_ms(started))
        except HttpTransportError:
            return _failed_probe(HealthFailure.CONNECTION, latency_ms=_latency_ms(started))
        latency_ms = _latency_ms(started)
        success, limited, failure = _classify_http_api(response)
        return EndpointProbeResult(
            checked_at=datetime.now(UTC),
            success=success,
            limited=limited,
            latency_ms=latency_ms,
            failure=failure,
        )
