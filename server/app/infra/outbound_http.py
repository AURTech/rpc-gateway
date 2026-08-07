from collections.abc import AsyncIterator, Iterable
from typing import Never, Protocol, runtime_checkable

import anyio
import httpcore
import httpx

from app.infra.outbound_policy import (
    IpAddress,
    OutboundTargetError,
    OutboundTargetPolicy,
    build_outbound_target_policy,
    parse_ip_address,
)


def _default_network_backend() -> httpcore.AsyncNetworkBackend:
    # Reason: httpcore conditionally exports AnyIOBackend with a wider type surface than its runtime base class.
    return httpcore.AnyIOBackend()  # pyright: ignore[reportReturnType]  # ty: ignore[invalid-return-type]


class PolicyNetworkBackend(httpcore.AsyncNetworkBackend):
    """Pin HTTP connections to policy-approved DNS answers and verify the peer."""

    def __init__(
        self,
        policy: OutboundTargetPolicy,
        *,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._policy = policy
        self._backend = backend or _default_network_backend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                addresses = await self._policy.get_connection_addresses(host, port)
                last_error: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
                for address in addresses:
                    try:
                        stream = await self._backend.connect_tcp(
                            str(address),
                            port,
                            timeout=timeout,
                            local_address=local_address,
                            socket_options=socket_options,
                        )
                    except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                        last_error = exc
                        continue
                    peer_address = _get_peer_address(stream)
                    if peer_address is None or not self._policy.is_address_allowed(peer_address):
                        await stream.aclose()
                        raise httpcore.ConnectError('Outbound connection peer address is not allowed.')
                    return stream
                if last_error is not None:
                    raise last_error
                raise httpcore.ConnectError('Outbound target connection failed.')
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout('Outbound target connection timed out.') from exc
        except OutboundTargetError as exc:
            raise httpcore.ConnectError(str(exc)) from exc

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        _ = path, timeout, socket_options
        raise httpcore.ConnectError('Outbound Unix socket connections are not allowed.')

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


@runtime_checkable
class _AsyncResponseStream(Protocol):
    def __aiter__(self) -> AsyncIterator[bytes]: ...

    async def aclose(self) -> None: ...


class _HttpCoreResponseStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: _AsyncResponseStream,
        request: httpx.Request,
    ) -> None:
        self._stream = stream
        self._request = request

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for part in self._stream:
                yield part
        except _HTTPCORE_ERRORS as exc:
            _raise_httpx_error(exc, self._request)

    async def aclose(self) -> None:
        try:
            await self._stream.aclose()
        except _HTTPCORE_ERRORS as exc:
            _raise_httpx_error(exc, self._request)


class OutboundHttpTransport(httpx.AsyncBaseTransport):
    """Adapt the guarded httpcore connection pool to the httpx transport API."""

    def __init__(
        self,
        *,
        policy: OutboundTargetPolicy | None = None,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        target_policy = policy or build_outbound_target_policy()
        backend = network_backend or PolicyNetworkBackend(target_policy)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpcore.default_ssl_context(),
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=5.0,
            network_backend=backend,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not isinstance(request.stream, httpx.AsyncByteStream):
            raise TypeError('Outbound HTTP request stream must be asynchronous.')
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            core_response = await self._pool.handle_async_request(core_request)
        except _HTTPCORE_ERRORS as exc:
            _raise_httpx_error(exc, request)
        if not isinstance(core_response.stream, _AsyncResponseStream):
            raise TypeError('Outbound HTTP response stream must be asynchronous.')
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_HttpCoreResponseStream(core_response.stream, request),
            extensions=core_response.extensions,
        )

    async def aclose(self) -> None:
        try:
            await self._pool.aclose()
        except _HTTPCORE_ERRORS as exc:
            _raise_httpx_error(exc, httpx.Request('GET', 'http://outbound.invalid'))


_HTTPCORE_ERRORS = (
    httpcore.TimeoutException,
    httpcore.NetworkError,
    httpcore.ProxyError,
    httpcore.UnsupportedProtocol,
    httpcore.ProtocolError,
)


def _get_peer_address(stream: httpcore.AsyncNetworkStream) -> IpAddress | None:
    value = stream.get_extra_info('server_addr')
    if isinstance(value, tuple) and value and isinstance(value[0], str):
        return parse_ip_address(value[0])
    return None


def _raise_httpx_error(exc: Exception, request: httpx.Request) -> Never:
    error_type: type[httpx.HTTPError]
    if isinstance(exc, httpcore.ConnectTimeout):
        error_type = httpx.ConnectTimeout
    elif isinstance(exc, httpcore.ReadTimeout):
        error_type = httpx.ReadTimeout
    elif isinstance(exc, httpcore.WriteTimeout):
        error_type = httpx.WriteTimeout
    elif isinstance(exc, httpcore.PoolTimeout):
        error_type = httpx.PoolTimeout
    elif isinstance(exc, httpcore.ConnectError):
        error_type = httpx.ConnectError
    elif isinstance(exc, httpcore.ReadError):
        error_type = httpx.ReadError
    elif isinstance(exc, httpcore.WriteError):
        error_type = httpx.WriteError
    elif isinstance(exc, httpcore.ProxyError):
        error_type = httpx.ProxyError
    elif isinstance(exc, httpcore.UnsupportedProtocol):
        error_type = httpx.UnsupportedProtocol
    elif isinstance(exc, httpcore.LocalProtocolError):
        error_type = httpx.LocalProtocolError
    elif isinstance(exc, httpcore.RemoteProtocolError):
        error_type = httpx.RemoteProtocolError
    elif isinstance(exc, httpcore.TimeoutException):
        error_type = httpx.TimeoutException
    elif isinstance(exc, httpcore.NetworkError):
        error_type = httpx.NetworkError
    else:
        error_type = httpx.ProtocolError
    raise error_type(str(exc), request=request) from exc
