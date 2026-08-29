from typing import Any, Final

from app.clients.provider.base import (
    AccountActiveCheck,
    DiscoveredEndpoint,
    ProviderDiscovery,
    ProviderDiscoveryConfig,
    ProviderDiscoveryError,
)
from app.clients.provider.http import get_json
from app.clients.provider.networks import EVM_NETWORK_BY_CHAIN_ID
from app.clients.provider.probe import validate_evm_provider_credential
from app.clients.transport import HttpAuth, HttpTransport
from app.model.endpoint import EndpointAuthType
from app.model.provider import ProviderVendor
from app.model.provider.capability import provider_transports

TENDERLY_NETWORKS_URL: Final = 'https://api.tenderly.co/api/v1/supported-networks'


class TenderlyProviderAdapter:
    vendor = ProviderVendor.TENDERLY

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def discover(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> ProviderDiscovery:
        await validate_evm_provider_credential(
            self._transport,
            'https://mainnet.gateway.tenderly.co',
            HttpAuth(type=EndpointAuthType.PATH_API_KEY, secret=config.credential),
            check_account_active,
            expected_chain_id=1,
        )
        payload = await get_json(self._transport, TENDERLY_NETWORKS_URL)
        networks = self._parse_networks(payload)
        if not networks:
            raise ProviderDiscoveryError('Tenderly returned no supported networks.')
        items = [
            DiscoveredEndpoint(
                external_id=f'tenderly:{chain_id}:{slug}',
                chain=chain,
                network=network,
                url=f'https://{slug}.gateway.tenderly.co',
                auth_type=EndpointAuthType.PATH_API_KEY,
                auth_secret=config.credential,
            )
            for chain_id, slug in sorted(networks.items())
            if (pair := EVM_NETWORK_BY_CHAIN_ID.get(chain_id)) is not None
            for chain, network in [pair]
            if provider_transports(ProviderVendor.TENDERLY, chain, network)
        ]
        return ProviderDiscovery(items=items)

    @staticmethod
    def _parse_networks(payload: Any) -> dict[int, str]:
        if not isinstance(payload, list):
            return {}
        networks: dict[int, str] = {}
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get('network_slugs'), dict):
                continue
            chain_id_value = item.get('chain_id')
            supported_features = item.get('supported_features')
            if not isinstance(supported_features, dict) or supported_features.get('node') is not True:
                continue
            slugs = item['network_slugs']
            slug = slugs.get('node_rpc_slug')
            if not isinstance(chain_id_value, str) or not isinstance(slug, str) or not slug:
                continue
            try:
                networks[int(chain_id_value)] = slug
            except ValueError:
                continue
        return networks
