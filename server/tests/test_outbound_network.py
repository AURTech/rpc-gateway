from collections.abc import Iterable
from ipaddress import IPv4Address, ip_address, ip_network

import anyio
import httpcore
import httpx
import pytest
from app.core.config import CONF
from app.infra import outbound_policy
from app.infra.http_client import build_outbound_http_client
from app.infra.outbound_http import OutboundHttpTransport, PolicyNetworkBackend
from app.infra.outbound_policy import OutboundTargetError, OutboundTargetPolicy, build_outbound_target_policy


class _FakeStream(httpcore.AsyncNetworkStream):
    def __init__(self, peer_address: str, response: bytes = b'') -> None:
        self.peer_address = peer_address
        self.response = response
        self.closed = False
        self.writes: list[bytes] = []
        self.tls_server_names: list[str | None] = []

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        _ = max_bytes, timeout
        response = self.response
        self.response = b''
        return response

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        _ = timeout
        self.writes.append(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: object,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        _ = ssl_context, timeout
        self.tls_server_names.append(server_hostname)
        return self

    def get_extra_info(self, info: str) -> object:
        if info == 'server_addr':
            return (self.peer_address, 443)
        if info == 'is_readable':
            return False
        return None


class _FakeNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, *, peer_address: str | None = None, response: bytes = b'') -> None:
        self.peer_address = peer_address
        self.response = response
        self.hosts: list[str] = []
        self.streams: list[_FakeStream] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        _ = port, timeout, local_address, socket_options
        self.hosts.append(host)
        stream = _FakeStream(self.peer_address or host, self.response)
        self.streams.append(stream)
        return stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        _ = path, timeout, socket_options
        raise AssertionError('Unix sockets must not be used.')

    async def sleep(self, seconds: float) -> None:
        _ = seconds


@pytest.mark.parametrize(
    'address',
    [
        '0.0.0.0',
        '10.1.2.3',
        '100.64.0.1',
        '127.0.0.1',
        '169.254.169.254',
        '192.0.2.1',
        '224.0.0.1',
        '::',
        '::1',
        'fe80::1',
        'ff02::1',
        '2001:db8::1',
    ],
)
def test_outbound_policy_blocks_non_public_addresses_by_default(address: str) -> None:
    policy = OutboundTargetPolicy()

    assert policy.is_address_allowed(ip_address(address)) is False


def test_outbound_policy_allows_public_and_configured_private_addresses() -> None:
    policy = OutboundTargetPolicy(
        private_networks=(ip_network('10.20.0.0/16'), ip_network('fd12:3456::/48')),
    )

    assert policy.is_address_allowed(ip_address('93.184.216.34')) is True
    assert policy.is_address_allowed(ip_address('2606:4700:4700::1111')) is True
    assert policy.is_address_allowed(ip_address('10.20.1.2')) is True
    assert policy.is_address_allowed(ip_address('fd12:3456::1')) is True
    assert policy.is_address_allowed(ip_address('10.21.1.2')) is False


def test_outbound_policy_builder_uses_configured_private_cidrs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CONF, 'OUTBOUND_PRIVATE_NETWORK_CIDRS', ['10.20.0.0/16', 'fd12:3456::/48'])

    policy = build_outbound_target_policy()

    assert policy.is_address_allowed(ip_address('10.20.1.2')) is True
    assert policy.is_address_allowed(ip_address('fd12:3456::1')) is True
    assert policy.is_address_allowed(ip_address('10.21.1.2')) is False


def test_outbound_policy_rejects_blocked_ip_literal_and_user_information() -> None:
    policy = OutboundTargetPolicy()

    with pytest.raises(OutboundTargetError, match='IP address is not allowed'):
        policy.parse_url('http://127.0.0.1:8545/path-key', allowed_schemes=frozenset({'http', 'https'}))
    with pytest.raises(OutboundTargetError, match='user information'):
        policy.parse_url('https://user:secret@rpc.example.test', allowed_schemes=frozenset({'http', 'https'}))


@pytest.mark.anyio
@pytest.mark.parametrize('validate_before_connection', [False, True])
async def test_outbound_policy_times_out_dns_lookup(
    monkeypatch: pytest.MonkeyPatch,
    validate_before_connection: bool,
) -> None:
    async def dns_lookup(_host: str, _port: int) -> tuple[IPv4Address, ...]:
        await anyio.sleep_forever()
        return (IPv4Address('93.184.216.34'),)

    monkeypatch.setattr(outbound_policy, 'OUTBOUND_DNS_LOOKUP_TIMEOUT_SECONDS', 0.01)
    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)

    with pytest.raises(OutboundTargetError, match='DNS lookup timed out'):
        if validate_before_connection:
            await policy.validate_url('https://rpc.example.test', allowed_schemes=frozenset({'http', 'https'}))
        else:
            await policy.get_connection_addresses('rpc.example.test', 443)


@pytest.mark.anyio
async def test_network_backend_pins_dns_lookup_to_an_allowed_ip() -> None:
    async def dns_lookup(host: str, port: int) -> tuple[IPv4Address, ...]:
        assert (host, port) == ('rpc.example.test', 443)
        return (IPv4Address('10.0.0.5'), IPv4Address('93.184.216.34'))

    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    backend = _FakeNetworkBackend()
    guarded = PolicyNetworkBackend(policy, backend=backend)

    stream = await guarded.connect_tcp('rpc.example.test', 443)

    assert backend.hosts == ['93.184.216.34']
    assert stream.get_extra_info('server_addr') == ('93.184.216.34', 443)


@pytest.mark.anyio
async def test_network_backend_rejects_dns_answers_without_connecting() -> None:
    async def dns_lookup(_host: str, _port: int) -> tuple[IPv4Address, ...]:
        return (IPv4Address('127.0.0.1'), IPv4Address('169.254.169.254'))

    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    backend = _FakeNetworkBackend()
    guarded = PolicyNetworkBackend(policy, backend=backend)

    with pytest.raises(httpcore.ConnectError, match='no allowed IP addresses'):
        await guarded.connect_tcp('rebind.example.test', 80)

    assert backend.hosts == []


@pytest.mark.anyio
async def test_network_backend_rejects_unexpected_connected_peer() -> None:
    async def dns_lookup(_host: str, _port: int) -> tuple[IPv4Address, ...]:
        return (IPv4Address('93.184.216.34'),)

    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    backend = _FakeNetworkBackend(peer_address='127.0.0.1')
    guarded = PolicyNetworkBackend(policy, backend=backend)

    with pytest.raises(httpcore.ConnectError, match='peer address is not allowed'):
        await guarded.connect_tcp('rebind.example.test', 80)

    assert backend.streams[0].closed is True


@pytest.mark.anyio
async def test_connection_rechecks_dns_after_save_time_validation() -> None:
    answers = [
        (IPv4Address('93.184.216.34'),),
        (IPv4Address('127.0.0.1'),),
    ]

    async def dns_lookup(_host: str, _port: int) -> tuple[IPv4Address, ...]:
        return answers.pop(0)

    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    backend = _FakeNetworkBackend()
    guarded = PolicyNetworkBackend(policy, backend=backend)

    await policy.validate_url('https://rebind.example.test/path-key', allowed_schemes=frozenset({'http', 'https'}))
    with pytest.raises(httpcore.ConnectError, match='no allowed IP addresses'):
        await guarded.connect_tcp('rebind.example.test', 443)

    assert answers == []
    assert backend.hosts == []


@pytest.mark.anyio
async def test_outbound_https_transport_connects_to_pinned_ip_with_original_host() -> None:
    async def dns_lookup(host: str, port: int) -> tuple[IPv4Address, ...]:
        assert (host, port) == ('rpc.example.test', 443)
        return (IPv4Address('93.184.216.34'),)

    response = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok'
    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    backend = _FakeNetworkBackend(response=response)
    network_backend = PolicyNetworkBackend(policy, backend=backend)
    transport = OutboundHttpTransport(policy=policy, network_backend=network_backend)

    async with httpx.AsyncClient(transport=transport) as client:
        result = await client.get('https://rpc.example.test/status')

    assert result.text == 'ok'
    assert backend.hosts == ['93.184.216.34']
    assert b'Host: rpc.example.test' in b''.join(backend.streams[0].writes)
    assert backend.streams[0].tls_server_names == ['rpc.example.test']


@pytest.mark.anyio
async def test_outbound_http_client_does_not_follow_redirects() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'http://127.0.0.1/internal'})

    async with build_outbound_http_client(transport=httpx.MockTransport(handler)) as client:
        response = await client.get('https://rpc.example.test')

    assert response.status_code == 302
    assert requests == ['https://rpc.example.test']


@pytest.mark.anyio
async def test_redirect_cannot_bypass_outbound_target_policy() -> None:
    async def dns_lookup(host: str, port: int) -> tuple[IPv4Address, ...]:
        assert (host, port) == ('rpc.example.test', 80)
        return (IPv4Address('93.184.216.34'),)

    redirect = b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/internal\r\nContent-Length: 0\r\n\r\n'
    policy = OutboundTargetPolicy(dns_lookup=dns_lookup)
    backend = _FakeNetworkBackend(response=redirect)
    network_backend = PolicyNetworkBackend(policy, backend=backend)
    transport = OutboundHttpTransport(policy=policy, network_backend=network_backend)

    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        with pytest.raises(httpx.ConnectError, match='no allowed IP addresses'):
            await client.get('http://rpc.example.test/start')

    assert backend.hosts == ['93.184.216.34']
