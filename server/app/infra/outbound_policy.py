import socket
from collections.abc import Awaitable, Callable, Sequence
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from urllib.parse import SplitResult, urlsplit

import anyio

from app.core.config import CONF

type IpAddress = IPv4Address | IPv6Address
type IpNetwork = IPv4Network | IPv6Network
type DnsLookup = Callable[[str, int], Awaitable[Sequence[IpAddress]]]

HTTP_OUTBOUND_SCHEMES = frozenset({'http', 'https'})
OUTBOUND_DEFAULT_PORTS = {
    'http': 80,
    'https': 443,
}
OUTBOUND_DNS_LOOKUP_TIMEOUT_SECONDS = 5.0


class OutboundTargetError(Exception):
    pass


async def lookup_ip_addresses(host: str, port: int) -> tuple[IpAddress, ...]:
    try:
        records = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise OutboundTargetError('Outbound target DNS lookup failed.') from exc

    addresses: list[IpAddress] = []
    seen: set[IpAddress] = set()
    for _family, _socket_type, _protocol, _canonical_name, socket_address in records:
        address = parse_ip_address(socket_address[0])
        if address is None or address in seen:
            continue
        addresses.append(address)
        seen.add(address)
    if not addresses:
        raise OutboundTargetError('Outbound target DNS lookup returned no IP addresses.')
    return tuple(addresses)


class OutboundTargetPolicy:
    """Return only outbound addresses permitted by the operations policy.

    Hostnames are looked up for every new connection. Callers must connect to
    the returned literal IP address so a later DNS answer cannot change the
    destination between policy evaluation and TCP connection setup.
    """

    def __init__(
        self,
        *,
        private_networks: Sequence[IpNetwork] = (),
        dns_lookup: DnsLookup = lookup_ip_addresses,
    ) -> None:
        self._private_networks = tuple(private_networks)
        self._dns_lookup = dns_lookup

    def parse_url(self, url: str, *, allowed_schemes: frozenset[str]) -> SplitResult:
        parts = urlsplit(url.strip())
        if parts.scheme not in allowed_schemes or not parts.netloc:
            raise OutboundTargetError('Outbound target URL scheme or authority is invalid.')
        if parts.username is not None or parts.password is not None:
            raise OutboundTargetError('Outbound target URL must not contain user information.')
        host = parts.hostname
        if host is None or not host.strip():
            raise OutboundTargetError('Outbound target URL host is invalid.')
        if '%' in host:
            raise OutboundTargetError('Outbound target URL must not contain a scoped IP address.')
        try:
            port = parts.port
        except ValueError as exc:
            raise OutboundTargetError('Outbound target URL port is invalid.') from exc
        if port == 0:
            raise OutboundTargetError('Outbound target URL port is invalid.')

        address = parse_ip_address(host)
        if address is not None and not self.is_address_allowed(address):
            raise OutboundTargetError('Outbound target IP address is not allowed.')
        return parts

    async def validate_url(self, url: str, *, allowed_schemes: frozenset[str]) -> SplitResult:
        """Check URL structure and its DNS answers before configuration is saved.

        Raises:
            OutboundTargetError: URL parsing, DNS lookup, or address policy fails.
        """
        parts = self.parse_url(url, allowed_schemes=allowed_schemes)
        host = parts.hostname
        if host is None:
            raise OutboundTargetError('Outbound target URL host is invalid.')
        port = parts.port
        if port is None:
            port = OUTBOUND_DEFAULT_PORTS.get(parts.scheme)
        if port is None:
            raise OutboundTargetError('Outbound target URL port is required.')
        await self.get_connection_addresses(host, port)
        return parts

    async def get_connection_addresses(self, host: str, port: int) -> tuple[IpAddress, ...]:
        """Return allowed literal addresses for one connection attempt.

        Raises:
            OutboundTargetError: DNS lookup fails or every address is blocked.
        """
        address = parse_ip_address(host)
        if address is not None:
            addresses = (address,)
        else:
            try:
                with anyio.fail_after(OUTBOUND_DNS_LOOKUP_TIMEOUT_SECONDS):
                    addresses = tuple(await self._dns_lookup(host, port))
            except TimeoutError as exc:
                raise OutboundTargetError('Outbound target DNS lookup timed out.') from exc
        allowed: list[IpAddress] = []
        seen: set[IpAddress] = set()
        for candidate in addresses:
            normalized = _normalize_ip_address(candidate)
            if normalized in seen or not self.is_address_allowed(normalized):
                continue
            allowed.append(normalized)
            seen.add(normalized)
        if not allowed:
            raise OutboundTargetError('Outbound target has no allowed IP addresses.')
        return tuple(allowed)

    def is_address_allowed(self, address: IpAddress) -> bool:
        normalized = _normalize_ip_address(address)
        if (
            normalized.is_loopback
            or normalized.is_link_local
            or normalized.is_multicast
            or normalized.is_unspecified
            or normalized.is_reserved
            or (isinstance(normalized, IPv6Address) and normalized.is_site_local)
        ):
            return False
        if normalized.is_global:
            return True
        return any(normalized.version == network.version and normalized in network for network in self._private_networks)


def build_outbound_target_policy() -> OutboundTargetPolicy:
    private_networks = tuple(ip_network(value) for value in CONF.OUTBOUND_PRIVATE_NETWORK_CIDRS)
    return OutboundTargetPolicy(private_networks=private_networks)


def parse_ip_address(value: str) -> IpAddress | None:
    try:
        return _normalize_ip_address(ip_address(value))
    except ValueError:
        return None


def _normalize_ip_address(address: IpAddress) -> IpAddress:
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address
