from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from app.model.endpoint import EndpointAuthType
from app.model.http_auth import PATH_API_KEY_PLACEHOLDER, validate_auth_header_name, validate_auth_query_param

STREAM_CHUNK_BYTES = 64 * 1024


class HttpTransportError(Exception):
    pass


class HttpTransportConfigError(HttpTransportError):
    pass


class HttpTransportConnectionError(HttpTransportError):
    pass


class HttpTransportTimeoutError(HttpTransportError):
    pass


class HttpTransportResponseError(HttpTransportError):
    pass


class HttpTransportResponseTooLargeError(HttpTransportResponseError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpAuth:
    type: EndpointAuthType = EndpointAuthType.NONE
    secret: str | None = field(default=None, repr=False)
    name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpTransportResponse:
    status_code: int
    headers: httpx.Headers
    body: bytes
    request_bytes: int
    response_bytes: int


def _auth_secret(auth: HttpAuth) -> str:
    secret = (auth.secret or '').strip()
    if not secret:
        raise HttpTransportConfigError('HTTP auth secret is required.')
    return secret


def inject_path_api_key(url: str, secret: str) -> str:
    """Insert one path credential without allowing ambiguous placeholder placement."""
    normalized_secret = secret.strip()
    if not normalized_secret:
        raise HttpTransportConfigError('HTTP auth secret is required.')
    parts = urlsplit(url)
    segments = parts.path.split('/')
    placeholder_count = segments.count(PATH_API_KEY_PLACEHOLDER)
    if placeholder_count > 1:
        raise HttpTransportConfigError('HTTP path auth placeholder is invalid.')
    encoded_secret = quote(normalized_secret, safe='')
    if placeholder_count == 1:
        path = '/'.join(encoded_secret if segment == PATH_API_KEY_PLACEHOLDER else segment for segment in segments)
    else:
        base_path = parts.path.rstrip('/')
        path = f'{base_path}/{encoded_secret}' if base_path else f'/{encoded_secret}'
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def apply_http_auth(url: str, headers: dict[str, str], auth: HttpAuth) -> tuple[str, dict[str, str]]:
    if auth.type is EndpointAuthType.NONE:
        if auth.secret is not None or auth.name is not None:
            raise HttpTransportConfigError('HTTP no-auth configuration is invalid.')
        return url, headers

    secret = _auth_secret(auth)
    normalized_headers = {name.lower() for name in headers}
    if auth.type is EndpointAuthType.BEARER:
        if 'authorization' in normalized_headers:
            raise HttpTransportConfigError('HTTP Authorization header conflicts with endpoint auth.')
        headers['Authorization'] = f'Bearer {secret}'
        return url, headers
    if auth.type is EndpointAuthType.HEADER_API_KEY:
        try:
            name = validate_auth_header_name(auth.name or '')
        except ValueError as exc:
            raise HttpTransportConfigError(str(exc)) from exc
        if name.lower() in normalized_headers:
            raise HttpTransportConfigError('HTTP header conflicts with endpoint auth.')
        headers[name] = secret
        return url, headers
    if auth.type is EndpointAuthType.QUERY_API_KEY:
        try:
            name = validate_auth_query_param(auth.name or '')
        except ValueError as exc:
            raise HttpTransportConfigError(str(exc)) from exc
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if any(key == name for key, _value in query):
            raise HttpTransportConfigError('HTTP query parameter conflicts with endpoint auth.')
        query.append((name, secret))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)), headers
    if auth.type is EndpointAuthType.PATH_API_KEY:
        return inject_path_api_key(url, secret), headers
    raise HttpTransportConfigError('HTTP auth type is unsupported.')


def _merge_query(
    url: str,
    query: Mapping[str, str | int | bool] | Sequence[tuple[str, str | int | bool]] | None,
) -> str:
    if not query:
        return url
    parts = urlsplit(url)
    values = parse_qsl(parts.query, keep_blank_values=True)
    # Reason: ty loses Mapping key/value parameters after narrowing this public union.
    items: Sequence[tuple[str, str | int | bool]] = (  # ty: ignore[invalid-assignment]
        tuple(query.items()) if isinstance(query, Mapping) else query
    )
    values.extend((name, str(value).lower() if isinstance(value, bool) else str(value)) for name, value in items)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(values), parts.fragment))


async def _read_response(response: httpx.Response, *, max_bytes: int | None) -> bytes:
    content_encoding = response.headers.get('content-encoding', 'identity').strip().lower()
    if content_encoding not in {'', 'identity'}:
        raise HttpTransportResponseError('HTTP response encoding is unsupported.')
    content_length = response.headers.get('content-length')
    if max_bytes is not None and content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HttpTransportResponseTooLargeError('HTTP response exceeded the configured size limit.')
        except ValueError:
            pass
    if response.is_stream_consumed:
        body = response.content
        if max_bytes is not None and len(body) > max_bytes:
            raise HttpTransportResponseTooLargeError('HTTP response exceeded the configured size limit.')
        return body
    body = bytearray()
    async for chunk in response.aiter_raw(chunk_size=STREAM_CHUNK_BYTES):
        if max_bytes is not None and len(body) + len(chunk) > max_bytes:
            raise HttpTransportResponseTooLargeError('HTTP response exceeded the configured size limit.')
        body.extend(chunk)
    return bytes(body)


class HttpTransport:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str | int | bool] | Sequence[tuple[str, str | int | bool]] | None = None,
        content: bytes | None = None,
        auth: HttpAuth | None = None,
        timeout: float = 10,
        max_response_bytes: int | None = None,
    ) -> HttpTransportResponse:
        """Send one optionally bounded request without retries, redirects, or secret-bearing errors."""
        request_headers = dict(headers or {})
        request_headers.setdefault('Accept-Encoding', 'identity')
        request_url = _merge_query(url.strip(), query)
        request_url, request_headers = apply_http_auth(request_url, request_headers, auth or HttpAuth())
        request_body = content or b''
        try:
            async with self._client.stream(
                method.upper(),
                request_url,
                headers=request_headers,
                content=request_body,
                timeout=timeout,
                follow_redirects=False,
            ) as response:
                response_body = await _read_response(response, max_bytes=max_response_bytes)
                return HttpTransportResponse(
                    status_code=response.status_code,
                    headers=response.headers,
                    body=response_body,
                    request_bytes=len(request_body),
                    response_bytes=len(response_body),
                )
        except HttpTransportError:
            raise
        except (httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise HttpTransportConnectionError('HTTP transport request failed.') from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise HttpTransportTimeoutError('HTTP transport request timed out.') from exc
        except httpx.InvalidURL as exc:
            raise HttpTransportConfigError('HTTP transport URL is invalid.') from exc
        except httpx.ConnectError as exc:
            raise HttpTransportConnectionError('HTTP transport request failed.') from exc
        except (httpx.ReadError, httpx.WriteError, httpx.ProtocolError) as exc:
            raise HttpTransportResponseError('HTTP transport protocol failed.') from exc
        except httpx.HTTPError as exc:
            raise HttpTransportConnectionError('HTTP transport request failed.') from exc
