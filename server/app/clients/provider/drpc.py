from typing import Any, Final
from urllib.parse import unquote, urlsplit

from app.clients.provider.base import (
    AccountActiveCheck,
    DiscoveredEndpoint,
    ProviderDiscovery,
    ProviderDiscoveryConfig,
    ProviderDiscoveryError,
)
from app.clients.provider.http import get_json
from app.clients.provider.networks import EVM_NETWORK_BY_CHAIN_ID
from app.clients.transport import PATH_API_KEY_PLACEHOLDER, HttpTransport
from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.endpoint import EndpointAuthType
from app.model.provider import ProviderVendor
from app.model.provider.capability import provider_networks

DRPC_NETWORKS_URL: Final = 'https://lb.drpc.org/networks'
DRPC_ENDPOINT_ORIGIN: Final = 'https://lb.drpc.live'
DRPC_NETWORK_NAMES: Final[dict[tuple[Chain, Network], str]] = {
    (Chain.ETHEREUM, Network.MAINNET): 'ethereum',
    (Chain.ETHEREUM, Network.SEPOLIA): 'sepolia',
    (Chain.OPTIMISM, Network.MAINNET): 'optimism',
    (Chain.OPTIMISM, Network.SEPOLIA): 'optimism-sepolia',
    (Chain.POLYGON, Network.MAINNET): 'polygon',
    (Chain.POLYGON, Network.AMOY): 'polygon-amoy',
    (Chain.ARBITRUM, Network.MAINNET): 'arbitrum',
    (Chain.ARBITRUM, Network.SEPOLIA): 'arbitrum-sepolia',
    (Chain.BASE, Network.MAINNET): 'base',
    (Chain.BASE, Network.SEPOLIA): 'base-sepolia',
    (Chain.BSC, Network.MAINNET): 'bsc',
    (Chain.BSC, Network.TESTNET): 'bsc-testnet',
    (Chain.SOLANA, Network.MAINNET_BETA): 'solana',
    (Chain.SOLANA, Network.DEVNET): 'solana-devnet',
    (Chain.BITCOIN, Network.MAINNET): 'bitcoin',
    (Chain.TRON, Network.MAINNET): 'tron',
}
DRPC_NETWORK_BY_NAME: Final = {name: pair for pair, name in DRPC_NETWORK_NAMES.items()}


class DrpcProviderAdapter:
    vendor = ProviderVendor.DRPC

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def discover(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> ProviderDiscovery:
        await check_account_active()
        credential = _credential_key(config.credential)
        complete = True
        try:
            networks = self._parse_networks(await get_json(self._transport, DRPC_NETWORKS_URL))
        except Exception:
            networks = dict(DRPC_NETWORK_NAMES)
            complete = False
        items = [
            DiscoveredEndpoint(
                external_id=self._external_id(pair, network_name),
                chain=pair[0],
                network=pair[1],
                url=f'{DRPC_ENDPOINT_ORIGIN}/{network_name}/{PATH_API_KEY_PLACEHOLDER}',
                auth_type=EndpointAuthType.PATH_API_KEY,
                auth_secret=credential,
                label=f'{config.name}-{pair[0].value}-{pair[1].value}',
            )
            for pair, network_name in sorted(networks.items(), key=lambda item: (item[0][0].value, item[0][1].value))
        ]
        return ProviderDiscovery(items=items, complete=complete)

    @staticmethod
    def _external_id(pair: tuple[Chain, Network], network_name: str) -> str:
        chain, network = pair
        chain_id = CHAIN_CATALOG[chain].networks[network].chain_id
        if CHAIN_CATALOG[chain].protocol is Protocol.EVM and chain_id is not None:
            return f'drpc:{chain_id}:{network_name}'
        return f'drpc:{network_name}:jsonrpc'

    @staticmethod
    def _parse_networks(payload: Any) -> dict[tuple[Chain, Network], str]:
        if not isinstance(payload, list):
            return {}
        supported = provider_networks(ProviderVendor.DRPC)
        candidates: dict[tuple[Chain, Network], tuple[str, int]] = {}
        for network in payload:
            if not isinstance(network, dict) or not isinstance(network.get('chains'), list):
                continue
            for chain in network['chains']:
                if not isinstance(chain, dict) or chain.get('api_type') != 'jsonrpc':
                    continue
                name = chain.get('name')
                if not isinstance(name, str):
                    continue
                pair = DRPC_NETWORK_BY_NAME.get(name)
                chain_id_value = chain.get('chain_id')
                if pair is None and chain.get('blockchain_type') == 'eth' and isinstance(chain_id_value, str):
                    try:
                        chain_id = int(chain_id_value.removeprefix('0x'), 16)
                    except ValueError:
                        continue
                    pair = EVM_NETWORK_BY_CHAIN_ID.get(chain_id)
                if pair is None or pair not in supported:
                    continue
                priority_value = chain.get('priority')
                priority = priority_value if isinstance(priority_value, int) else 0
                if pair not in candidates or priority > candidates[pair][1]:
                    candidates[pair] = (name, priority)
        return {pair: value[0] for pair, value in candidates.items()}


def _credential_key(value: str) -> str:
    credential = value.strip()
    if not credential:
        raise ProviderDiscoveryError('dRPC credential is required.')
    if '://' not in credential:
        if any(character in credential for character in '/:?#'):
            raise ProviderDiscoveryError('dRPC credential must be an API key or a standard endpoint URL.')
        return credential

    parts = urlsplit(credential.rstrip('/'))
    if parts.scheme != 'https' or parts.netloc.casefold() != 'lb.drpc.live' or parts.query or parts.fragment:
        raise ProviderDiscoveryError('dRPC endpoint URL is invalid.')
    segments = [unquote(segment) for segment in parts.path.split('/') if segment]
    if len(segments) != 2 or segments[0] not in DRPC_NETWORK_BY_NAME:
        raise ProviderDiscoveryError('dRPC endpoint URL path is invalid.')
    key = segments[1]
    if not key or any(character.isspace() or character in '/:?#' for character in key):
        raise ProviderDiscoveryError('dRPC endpoint URL key is invalid.')
    return key
