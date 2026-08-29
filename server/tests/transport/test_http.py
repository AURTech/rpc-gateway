from collections.abc import AsyncIterator

import httpx
import pytest
from app.clients.endpoint import EndpointConnection, EndpointHttpClient
from app.clients.transport import HttpAuth, HttpTransport, HttpTransportConfigError, HttpTransportError
from app.model.endpoint import EndpointAuthType, EndpointHttpApiRequest, EndpointJsonRpcRequest


class _ChunkedStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'123'
        yield b'45'


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('auth', 'expected_path', 'expected_header'),
    [
        (HttpAuth(type=EndpointAuthType.BEARER, secret='bearer-secret'), '/rpc', ('authorization', 'Bearer bearer-secret')),
        (
            HttpAuth(type=EndpointAuthType.HEADER_API_KEY, name='x-api-key', secret='header-secret'),
            '/rpc',
            ('x-api-key', 'header-secret'),
        ),
        (HttpAuth(type=EndpointAuthType.PATH_API_KEY, secret='path / secret'), '/rpc/path%20%2F%20secret', None),
    ],
)
async def test_http_transport_applies_auth_without_exposing_it(
    auth: HttpAuth,
    expected_path: str,
    expected_header: tuple[str, str] | None,
) -> None:
    requests: list[httpx.Request] = []

    async def send(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b'ok')

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        response = await HttpTransport(client).request('POST', 'https://rpc.example.test/rpc', auth=auth, content=b'{}')

    assert response.body == b'ok'
    assert response.request_bytes == 2
    assert requests[0].url.raw_path == expected_path.encode()
    if expected_header is not None:
        assert requests[0].headers[expected_header[0]] == expected_header[1]
    assert 'secret' not in repr(auth)


@pytest.mark.anyio
async def test_http_transport_merges_query_auth_and_preserves_status() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        assert request.url.params['network'] == 'ethereum'
        assert request.url.params['dkey'] == 'query-secret'
        return httpx.Response(503, content=b'unavailable')

    auth = HttpAuth(type=EndpointAuthType.QUERY_API_KEY, name='dkey', secret='query-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        response = await HttpTransport(client).request(
            'GET',
            'https://rpc.example.test/rpc',
            query={'network': 'ethereum'},
            auth=auth,
        )

    assert response.status_code == 503
    assert response.body == b'unavailable'


@pytest.mark.anyio
async def test_http_transport_injects_path_auth_before_a_network_suffix() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b'/base/path-secret/solana-mainnet'
        return httpx.Response(200, content=b'ok')

    auth = HttpAuth(type=EndpointAuthType.PATH_API_KEY, secret='path-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        response = await HttpTransport(client).request(
            'POST',
            'https://rpc.example.test/base/{api_key}/solana-mainnet',
            auth=auth,
        )

    assert response.body == b'ok'


@pytest.mark.anyio
async def test_http_transport_preserves_repeated_query_order() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        assert request.url.query == b'value=1&value=2&empty='
        return httpx.Response(200, content=b'ok')

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        response = await HttpTransport(client).request(
            'GET',
            'https://rpc.example.test/path',
            query=(('value', '1'), ('value', '2'), ('empty', '')),
        )

    assert response.body == b'ok'


@pytest.mark.anyio
async def test_http_transport_rejects_auth_conflicts_and_large_responses() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b'12345'))
    async with httpx.AsyncClient(transport=transport) as client:
        transport = HttpTransport(client)
        with pytest.raises(HttpTransportConfigError, match='conflicts'):
            await transport.request(
                'GET',
                'https://rpc.example.test/?token=existing',
                auth=HttpAuth(type=EndpointAuthType.QUERY_API_KEY, name='token', secret='secret'),
            )
        response = await transport.request('GET', 'https://rpc.example.test/')
        assert response.body == b'12345'
        with pytest.raises(HttpTransportError, match='size limit'):
            await transport.request('GET', 'https://rpc.example.test/', max_response_bytes=4)


@pytest.mark.anyio
async def test_http_transport_only_limits_explicitly_bounded_chunked_responses() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, stream=_ChunkedStream()))
    async with httpx.AsyncClient(transport=transport) as client:
        response = await HttpTransport(client).request('GET', 'https://rpc.example.test/')
        assert response.body == b'12345'
        with pytest.raises(HttpTransportError, match='size limit'):
            await HttpTransport(client).request('GET', 'https://rpc.example.test/', max_response_bytes=4)


def test_endpoint_business_request_defaults() -> None:
    jsonrpc_request = EndpointJsonRpcRequest(content=b'{}')
    http_api_request = EndpointHttpApiRequest(method='GET', path='/')

    assert jsonrpc_request.timeout == 6
    assert http_api_request.timeout == 6
    assert jsonrpc_request.max_response_bytes is None
    assert http_api_request.max_response_bytes is None


@pytest.mark.anyio
async def test_http_api_client_rejects_absolute_and_parent_paths() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200))) as client:
        endpoint_client = EndpointHttpClient(HttpTransport(client))
        connection = EndpointConnection(url='https://rpc.example.test/base', auth=HttpAuth())
        with pytest.raises(HttpTransportConfigError):
            await endpoint_client.request_http_api(connection, 'GET', 'https://attacker.example.test/path')
        with pytest.raises(HttpTransportConfigError):
            await endpoint_client.request_http_api(connection, 'GET', '../admin')
        with pytest.raises(HttpTransportConfigError):
            await endpoint_client.request_http_api(connection, 'GET', '%252e%252e/admin')
        with pytest.raises(HttpTransportConfigError):
            await endpoint_client.request_http_api(connection, 'GET', '..\\admin')


@pytest.mark.anyio
async def test_http_transport_uses_sanitized_network_errors() -> None:
    async def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f'failed for {request.url}', request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(HttpTransportError) as error:
            await HttpTransport(client).request(
                'GET',
                'https://rpc.example.test/private-secret',
                auth=HttpAuth(type=EndpointAuthType.BEARER, secret='bearer-secret'),
            )
    assert str(error.value) == 'HTTP transport request failed.'
    assert 'private-secret' not in str(error.value)
    assert 'bearer-secret' not in str(error.value)
