from urllib.parse import urlsplit

from app.core.config import CONF
from app.model.blockchain import CHAIN_CATALOG, Chain, Network
from app.model.gateway import GatewayAccessPoint
from app.model.transport import Transport

_MAINNET_NETWORKS = (Network.MAINNET, Network.MAINNET_BETA)
_CHAIN_SLUGS: dict[Chain, str] = {
    Chain.ETHEREUM: 'ether',
    Chain.POLYGON: 'poly',
    Chain.BSC: 'bnb',
    Chain.ARBITRUM: 'arb',
    Chain.OPTIMISM: 'op',
    Chain.BASE: 'base',
    Chain.SOLANA: 'sol',
    Chain.BITCOIN: 'btc',
    Chain.LITECOIN: 'ltc',
    Chain.TRON: 'tron',
}
_NETWORK_SLUGS: dict[tuple[Chain, Network], str] = {
    (Chain.TRON, Network.NILE): 'testnet',
}
_TRANSPORT_SLUGS: dict[Transport, str] = {
    Transport.JSONRPC: 'jsonrpc',
    Transport.HTTP_API: 'httpapi',
}
API_KEY_TEMPLATE = '{api_key}'


def build_access_points(chain: Chain, network: Network, values: object) -> list[GatewayAccessPoint]:
    transports = parse_transport_snapshot(chain, network, values)
    return [
        GatewayAccessPoint(transport=transport, url=build_gateway_url(chain, network, transport)) for transport in transports
    ]


def parse_transport_snapshot(chain: Chain, network: Network, values: object) -> tuple[Transport, ...]:
    definition = CHAIN_CATALOG.get(chain)
    if definition is None or network not in definition.networks:
        raise ValueError('Gateway chain and network are not supported.')
    if not isinstance(values, list) or not values:
        raise ValueError('Gateway transport snapshot is invalid.')
    transports: list[Transport] = []
    seen: set[Transport] = set()
    for raw in values:
        try:
            transport = Transport(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError('Gateway transport snapshot is invalid.') from exc
        if transport in seen:
            raise ValueError('Gateway transport snapshot cannot contain duplicates.')
        transports.append(transport)
        seen.add(transport)
    return tuple(transports)


def build_gateway_url(chain: Chain, network: Network, transport: Transport) -> str:
    host = build_gateway_host(chain, network, transport)
    domain = _gateway_base_domain()
    return f'https://{host}.{domain}/{API_KEY_TEMPLATE}'


def build_gateway_host(chain: Chain, network: Network, transport: Transport) -> str:
    definition = CHAIN_CATALOG.get(chain)
    if definition is None or network not in definition.networks:
        raise ValueError('Gateway chain and network are not supported.')
    if transport not in definition.networks[network].gateway_transports:
        raise ValueError('Gateway transport is not supported.')
    chain_slug = _CHAIN_SLUGS[chain]
    network_slug = None if network in _MAINNET_NETWORKS else _NETWORK_SLUGS.get((chain, network), network.value)
    host_prefix = chain_slug if network_slug is None else f'{chain_slug}-{network_slug}'
    return f'{host_prefix}-{_TRANSPORT_SLUGS[transport]}'


def parse_gateway_host(value: str | None, expected_transport: Transport) -> tuple[Chain, Network]:
    host = _host_without_port(value)
    domain = _host_without_port(_gateway_base_domain())
    if host is None or not domain or not host.endswith(f'.{domain}'):
        raise ValueError('Gateway host is invalid.')
    prefix = host.removesuffix(f'.{domain}')
    matches = [
        (chain, network)
        for chain, definition in CHAIN_CATALOG.items()
        for network in definition.networks
        if expected_transport in definition.networks[network].gateway_transports
        and build_gateway_host(chain, network, expected_transport) == prefix
    ]
    if len(matches) != 1:
        raise ValueError('Gateway host is invalid.')
    return matches[0]


def is_gateway_host(value: str | None) -> bool:
    for transport in Transport:
        try:
            parse_gateway_host(value, transport)
        except ValueError:
            continue
        return True
    return False


def _gateway_base_domain() -> str:
    configured = CONF.PUBLIC_RPC_GATEWAY_BASE_DOMAIN.strip().lower().removeprefix('https://').removeprefix('http://')
    if configured:
        return configured.rstrip('/.')
    parsed = urlsplit(CONF.PUBLIC_RPC_API_BASE_URL)
    return (parsed.netloc or parsed.path).strip().lower().rstrip('/.')


def _host_without_port(value: str | None) -> str | None:
    if not value:
        return None
    host = value.strip().lower().rstrip('.')
    if not host:
        return None
    if host.startswith('['):
        end = host.find(']')
        return host[: end + 1] if end >= 0 else host
    return host.rsplit(':', 1)[0]
