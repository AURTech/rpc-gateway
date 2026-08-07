from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit

from app.clients.provider.base import (
    AccountActiveCheck,
    DiscoveredEndpoint,
    ProviderDiscovery,
    ProviderDiscoveryConfig,
    ProviderDiscoveryError,
    ProviderDiscoveryFailure,
)
from app.clients.provider.http import get_json
from app.clients.transport import HttpAuth, HttpTransport
from app.model.blockchain import Chain, Network, validate_chain_network
from app.model.endpoint import EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderVendor
from app.model.provider.capability import provider_transports

CHAINSTACK_NODES_URL: Final = 'https://api.chainstack.com/v1/nodes/'
CHAINSTACK_NODES_V2_URL: Final = 'https://api.chainstack.com/v2/nodes/'

_CHAIN_BY_PROTOCOL: Final[dict[str, Chain]] = {
    'ethereum': Chain.ETHEREUM,
    'polygon': Chain.POLYGON,
    'polygon-pos': Chain.POLYGON,
    'bsc': Chain.BSC,
    'bnb': Chain.BSC,
    'bnb-smart-chain': Chain.BSC,
    'arbitrum': Chain.ARBITRUM,
    'optimism': Chain.OPTIMISM,
    'base': Chain.BASE,
    'solana': Chain.SOLANA,
    'bitcoin': Chain.BITCOIN,
    'litecoin': Chain.LITECOIN,
    'tron': Chain.TRON,
}
_NETWORK_BY_NAME: Final[dict[str, Network]] = {
    'mainnet': Network.MAINNET,
    'mainnet-beta': Network.MAINNET_BETA,
    'sepolia': Network.SEPOLIA,
    'sepolia-testnet': Network.SEPOLIA,
    'amoy': Network.AMOY,
    'amoy-testnet': Network.AMOY,
    'testnet': Network.TESTNET,
    'devnet': Network.DEVNET,
    'nile': Network.NILE,
    'nile-testnet': Network.NILE,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class ChainstackEndpoint:
    id: str
    url: str
    path_secret: str | None


class ChainstackProviderAdapter:
    vendor = ProviderVendor.CHAINSTACK

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def discover(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> ProviderDiscovery:
        endpoints = await self._fetch_endpoints(config, check_account_active)
        try:
            metadata = await self._fetch_metadata(config, check_account_active)
        except Exception:
            return ProviderDiscovery(
                items=[],
                failures=[ProviderDiscoveryFailure(external_id=None, error='Chainstack node metadata failed.')],
                complete=False,
            )

        items: list[DiscoveredEndpoint] = []
        failures: list[ProviderDiscoveryFailure] = []
        complete = True
        for endpoint in endpoints:
            if endpoint.id not in metadata:
                complete = False
                failures.append(
                    ProviderDiscoveryFailure(
                        external_id=f'chainstack:{endpoint.id}',
                        error='Chainstack node metadata is missing.',
                    )
                )
                continue
            pair = metadata[endpoint.id]
            if pair is None:
                continue
            items.extend(self._build_items(config.name, endpoint, pair))
        return ProviderDiscovery(items=items, failures=failures, complete=complete)

    async def _fetch_endpoints(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> list[ChainstackEndpoint]:
        settings = config.settings.model_dump(exclude_none=True)
        query = {
            name: value
            for name, value in settings.items()
            if name in {'project', 'organization', 'region', 'provider', 'type'} and isinstance(value, str)
        }
        payloads = await self._fetch_pages(
            CHAINSTACK_NODES_URL,
            config.credential,
            check_account_active,
            query=query,
        )
        endpoints: list[ChainstackEndpoint] = []
        for value in payloads:
            endpoint = self._parse_endpoint(value)
            if endpoint is not None:
                endpoints.append(endpoint)
        return endpoints

    async def _fetch_metadata(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> dict[str, tuple[Chain, Network] | None]:
        payloads = await self._fetch_pages(CHAINSTACK_NODES_V2_URL, config.credential, check_account_active)
        metadata: dict[str, tuple[Chain, Network] | None] = {}
        for value in payloads:
            if not isinstance(value, dict):
                continue
            endpoint_id = value.get('id')
            protocol = value.get('protocol')
            network = value.get('network')
            if not isinstance(endpoint_id, str) or not endpoint_id:
                continue
            if not isinstance(protocol, str) or not isinstance(network, str):
                continue
            metadata[endpoint_id] = self._network_pair(protocol, network)
        return metadata

    async def _fetch_pages(
        self,
        url: str,
        credential: str,
        check_account_active: AccountActiveCheck,
        *,
        query: dict[str, str] | None = None,
    ) -> list[Any]:
        results: list[Any] = []
        next_url: str | None = url
        first_page = True
        while next_url is not None:
            await check_account_active()
            payload = await get_json(
                self._transport,
                next_url,
                query=query if first_page else None,
                auth=HttpAuth(type=EndpointAuthType.BEARER, secret=credential),
            )
            if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
                raise ProviderDiscoveryError('Chainstack API response is invalid.')
            results.extend(payload['results'])
            raw_next = payload.get('next')
            next_url = self._validate_next_url(raw_next) if isinstance(raw_next, str) and raw_next else None
            first_page = False
        return results

    @staticmethod
    def _build_items(
        name: str,
        endpoint: ChainstackEndpoint,
        pair: tuple[Chain, Network],
    ) -> list[DiscoveredEndpoint]:
        chain, network = pair
        items: list[DiscoveredEndpoint] = []
        for transport in sorted(provider_transports(ProviderVendor.CHAINSTACK, chain, network), key=lambda item: item.value):
            protocol = EndpointProtocol(transport.value)
            external_id = f'chainstack:{endpoint.id}'
            if protocol is EndpointProtocol.HTTP_API:
                external_id = f'{external_id}:{protocol.value}'
            items.append(
                DiscoveredEndpoint(
                    external_id=external_id,
                    chain=chain,
                    network=network,
                    protocol=protocol,
                    url=endpoint.url,
                    auth_type=EndpointAuthType.PATH_API_KEY if endpoint.path_secret else EndpointAuthType.NONE,
                    auth_secret=endpoint.path_secret,
                    label=f'{name}-{chain.value}-{network.value}-{protocol.value}-{endpoint.id}',
                )
            )
        return items

    @staticmethod
    def _network_pair(protocol: str, network: str) -> tuple[Chain, Network] | None:
        normalized_protocol = protocol.strip().casefold().replace('_', '-').replace(' ', '-')
        chain = _CHAIN_BY_PROTOCOL.get(normalized_protocol)
        if chain is None:
            return None
        normalized_network = network.strip().casefold().replace('_', '-').replace(' ', '-')
        for prefix in (f'{normalized_protocol}-', f'{chain.value}-'):
            if normalized_network.startswith(prefix):
                normalized_network = normalized_network.removeprefix(prefix)
                break
        network_value = _NETWORK_BY_NAME.get(normalized_network)
        if chain is Chain.SOLANA and network_value is Network.MAINNET:
            network_value = Network.MAINNET_BETA
        if network_value is None:
            return None
        try:
            pair = (chain, network_value)
            validate_chain_network(*pair)
        except ValueError:
            return None
        if not provider_transports(ProviderVendor.CHAINSTACK, *pair):
            return None
        return pair

    @staticmethod
    def _validate_next_url(value: str) -> str:
        parts = urlsplit(value)
        try:
            port = parts.port
        except ValueError as exc:
            raise ProviderDiscoveryError('Chainstack pagination URL is invalid.') from exc
        if (
            parts.scheme != 'https'
            or parts.hostname != 'api.chainstack.com'
            or port not in {None, 443}
            or parts.username is not None
            or parts.password is not None
        ):
            raise ProviderDiscoveryError('Chainstack pagination URL is invalid.')
        return value

    @staticmethod
    def _parse_endpoint(value: Any) -> ChainstackEndpoint | None:
        if not isinstance(value, dict) or value.get('status') != 'running':
            return None
        endpoint_id = value.get('id')
        details = value.get('details')
        if not isinstance(endpoint_id, str) or not endpoint_id or not isinstance(details, dict):
            return None
        http_url = details.get('https_endpoint')
        if not isinstance(http_url, str) or not http_url:
            return None
        auth_key = details.get('auth_key')
        if isinstance(auth_key, str) and auth_key.strip('/'):
            return ChainstackEndpoint(id=endpoint_id, url=http_url.rstrip('/'), path_secret=auth_key.strip('/'))
        parts = urlsplit(http_url.rstrip('/'))
        if not parts.path or parts.path == '/':
            return ChainstackEndpoint(id=endpoint_id, url=http_url.rstrip('/'), path_secret=None)
        base_path, _, secret = parts.path.rstrip('/').rpartition('/')
        url = urlunsplit((parts.scheme, parts.netloc, base_path, parts.query, parts.fragment))
        return ChainstackEndpoint(id=endpoint_id, url=url, path_secret=secret or None)
