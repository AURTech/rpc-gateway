from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

from app.clients.transport import HttpAuth, HttpTransport, HttpTransportConfigError, HttpTransportResponse, apply_http_auth


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointConnection:
    url: str
    auth: HttpAuth

    @property
    def effective_url(self) -> str:
        return apply_http_auth(self.url, {}, self.auth)[0]


def _join_endpoint_path(base_url: str, path: str) -> str:
    relative = urlsplit(path)
    decoded_path = relative.path
    for _attempt in range(3):
        next_path = unquote(decoded_path)
        if next_path == decoded_path:
            break
        decoded_path = next_path
    path_parts = decoded_path.replace('\\', '/').split('/')
    if relative.scheme or relative.netloc or any(part == '..' for part in path_parts):
        raise HttpTransportConfigError('HTTP API request path is invalid.')
    base = urlsplit(base_url)
    base_path = base.path.rstrip('/')
    request_path = relative.path.lstrip('/')
    joined_path = f'{base_path}/{request_path}' if request_path else base_path or '/'
    return urlunsplit((base.scheme, base.netloc, joined_path, relative.query, ''))


class EndpointHttpClient:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def request_jsonrpc(
        self,
        connection: EndpointConnection,
        content: bytes,
        *,
        timeout: float = 6,
        max_response_bytes: int | None = None,
    ) -> HttpTransportResponse:
        return await self._transport.request(
            'POST',
            connection.url,
            headers={'Content-Type': 'application/json'},
            content=content,
            auth=connection.auth,
            timeout=timeout,
            max_response_bytes=max_response_bytes,
        )

    async def request_http_api(
        self,
        connection: EndpointConnection,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str | int | bool] | Sequence[tuple[str, str | int | bool]] | None = None,
        content: bytes | None = None,
        timeout: float = 6,
        max_response_bytes: int | None = None,
    ) -> HttpTransportResponse:
        url = _join_endpoint_path(connection.url, path)
        return await self._transport.request(
            method,
            url,
            headers=headers,
            query=query,
            content=content,
            auth=connection.auth,
            timeout=timeout,
            max_response_bytes=max_response_bytes,
        )
