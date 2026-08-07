from typing import Any, Final

from app.clients.provider.base import AccountActiveCheck, DiscoveredEndpoint, ProviderDiscovery, ProviderDiscoveryConfig
from app.clients.provider.http import get_json
from app.clients.provider.networks import EVM_NETWORK_BY_CHAIN_ID
from app.clients.transport import HttpTransport
from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.endpoint import EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderVendor
from app.model.provider.capability import provider_transports

ALCHEMY_NETWORKS_URL: Final = 'https://app-api.alchemy.com/trpc/config.getNetworkConfig'
ALCHEMY_NETWORK_SUBDOMAINS: Final[dict[tuple[Chain, Network], str]] = {
    (Chain.ETHEREUM, Network.MAINNET): 'eth-mainnet',
    (Chain.ETHEREUM, Network.SEPOLIA): 'eth-sepolia',
    (Chain.OPTIMISM, Network.MAINNET): 'opt-mainnet',
    (Chain.OPTIMISM, Network.SEPOLIA): 'opt-sepolia',
    (Chain.POLYGON, Network.MAINNET): 'polygon-mainnet',
    (Chain.POLYGON, Network.AMOY): 'polygon-amoy',
    (Chain.ARBITRUM, Network.MAINNET): 'arb-mainnet',
    (Chain.ARBITRUM, Network.SEPOLIA): 'arb-sepolia',
    (Chain.BASE, Network.MAINNET): 'base-mainnet',
    (Chain.BASE, Network.SEPOLIA): 'base-sepolia',
    (Chain.BSC, Network.MAINNET): 'bnb-mainnet',
    (Chain.BSC, Network.TESTNET): 'bnb-testnet',
    (Chain.SOLANA, Network.MAINNET_BETA): 'solana-mainnet',
    (Chain.SOLANA, Network.DEVNET): 'solana-devnet',
    (Chain.BITCOIN, Network.MAINNET): 'bitcoin-mainnet',
    (Chain.BITCOIN, Network.TESTNET): 'bitcoin-testnet',
    (Chain.LITECOIN, Network.MAINNET): 'litecoin-mainnet',
    (Chain.LITECOIN, Network.TESTNET): 'litecoin-testnet',
    (Chain.TRON, Network.MAINNET): 'tron-mainnet',
    (Chain.TRON, Network.NILE): 'tron-testnet',
}
ALCHEMY_NETWORK_BY_SUBDOMAIN: Final = {subdomain: pair for pair, subdomain in ALCHEMY_NETWORK_SUBDOMAINS.items()}


class AlchemyProviderAdapter:
    vendor = ProviderVendor.ALCHEMY

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def discover(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> ProviderDiscovery:
        await check_account_active()
        complete = True
        networks = dict(ALCHEMY_NETWORK_SUBDOMAINS)
        try:
            networks.update(self._parse_networks(await get_json(self._transport, ALCHEMY_NETWORKS_URL)))
        except Exception:
            complete = False
        items: list[DiscoveredEndpoint] = []
        sorted_networks = sorted(networks.items(), key=lambda item: (item[0][0].value, item[0][1].value))
        for pair, subdomain in sorted_networks:
            chain, network = pair
            transports = sorted(provider_transports(self.vendor, chain, network), key=lambda item: item.value)
            for transport in transports:
                protocol = EndpointProtocol(transport.value)
                items.append(self._build_item(config, pair, subdomain, protocol))
        return ProviderDiscovery(items=items, complete=complete)

    @staticmethod
    def _build_item(
        config: ProviderDiscoveryConfig,
        pair: tuple[Chain, Network],
        subdomain: str,
        protocol: EndpointProtocol,
    ) -> DiscoveredEndpoint:
        chain, network = pair
        chain_id = CHAIN_CATALOG[chain].networks[network].chain_id
        if CHAIN_CATALOG[chain].protocol is Protocol.EVM and chain_id is not None:
            external_id = f'alchemy:{chain_id}'
        else:
            external_id = f'alchemy:{subdomain}:{protocol.value}'
        return DiscoveredEndpoint(
            external_id=external_id,
            chain=chain,
            network=network,
            protocol=protocol,
            url=f'https://{subdomain}.g.alchemy.com/v2',
            auth_type=EndpointAuthType.PATH_API_KEY,
            auth_secret=config.credential,
            label=f'{config.name}-{chain.value}-{network.value}-{protocol.value}',
        )

    @staticmethod
    def _parse_networks(payload: Any) -> dict[tuple[Chain, Network], str]:
        if not isinstance(payload, dict):
            return {}
        result = payload.get('result')
        data = result.get('data') if isinstance(result, dict) else None
        if not isinstance(data, list):
            return {}
        networks: dict[tuple[Chain, Network], str] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            subdomain = item.get('kebabCaseId')
            if not isinstance(subdomain, str) or not subdomain:
                continue
            pair = ALCHEMY_NETWORK_BY_SUBDOMAIN.get(subdomain)
            chain_id_value = item.get('networkChainId')
            if pair is None and isinstance(chain_id_value, int):
                pair = EVM_NETWORK_BY_CHAIN_ID.get(chain_id_value)
            elif pair is None and isinstance(chain_id_value, str) and chain_id_value.isdigit():
                pair = EVM_NETWORK_BY_CHAIN_ID.get(int(chain_id_value))
            if pair is not None and provider_transports(ProviderVendor.ALCHEMY, *pair):
                networks[pair] = subdomain
        return networks
