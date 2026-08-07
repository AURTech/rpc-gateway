from dataclasses import dataclass, replace
from typing import Any, Final
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from app.clients.provider.base import (
    AccountActiveCheck,
    DiscoveredEndpoint,
    ProviderDiscovery,
    ProviderDiscoveryConfig,
    ProviderDiscoveryError,
    ProviderDiscoveryFailure,
)
from app.clients.provider.http import get_json
from app.clients.transport import PATH_API_KEY_PLACEHOLDER, HttpAuth, HttpTransport
from app.model.blockchain import Chain, Network, validate_chain_network
from app.model.endpoint import EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderVendor

QUICKNODE_ENDPOINTS_URL: Final = 'https://api.quicknode.com/v0/endpoints'
QUICKNODE_CHAINS_URL: Final = 'https://api.quicknode.com/v0/chains'

_CHAIN_BY_SLUG: Final[dict[str, Chain]] = {
    'ethereum': Chain.ETHEREUM,
    'eth': Chain.ETHEREUM,
    'polygon': Chain.POLYGON,
    'matic': Chain.POLYGON,
    'bsc': Chain.BSC,
    'bnb': Chain.BSC,
    'bnb-smart-chain': Chain.BSC,
    'arbitrum': Chain.ARBITRUM,
    'arb': Chain.ARBITRUM,
    'optimism': Chain.OPTIMISM,
    'op': Chain.OPTIMISM,
    'base': Chain.BASE,
    'solana': Chain.SOLANA,
    'sol': Chain.SOLANA,
    'bitcoin': Chain.BITCOIN,
    'btc': Chain.BITCOIN,
    'litecoin': Chain.LITECOIN,
    'ltc': Chain.LITECOIN,
    'tron': Chain.TRON,
    'trx': Chain.TRON,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class QuicknodeEndpoint:
    id: str
    http_url: str
    chain_slug: str
    network_slug: str
    multichain: bool
    status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QuicknodeNetworkUrl:
    key: str
    http_url: str


class QuicknodeProviderAdapter:
    vendor = ProviderVendor.QUICKNODE

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def discover(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> ProviderDiscovery:
        endpoints = await self._fetch_endpoints(config, check_account_active)
        network_pairs: dict[str, tuple[Chain, Network]] = {}
        failures: list[ProviderDiscoveryFailure] = []
        complete = True
        if any(endpoint.multichain for endpoint in endpoints):
            await check_account_active()
            try:
                network_pairs = await self._fetch_network_pairs(config)
            except Exception:
                complete = False
                failures.append(ProviderDiscoveryFailure(external_id=None, error='QuickNode network catalog failed.'))

        items: list[DiscoveredEndpoint] = []
        for endpoint in endpoints:
            legacy_external_id = f'quicknode:{endpoint.id}'
            if endpoint.status != 'active':
                complete = False
                failures.append(
                    ProviderDiscoveryFailure(
                        external_id=legacy_external_id,
                        error='QuickNode endpoint is not active.',
                    )
                )
                continue
            if not endpoint.multichain:
                pair = _network_pair(endpoint.chain_slug, endpoint.network_slug)
                if pair is not None:
                    items.extend(self._build_items(config.name, endpoint.id, endpoint.http_url, pair))
                continue
            await check_account_active()
            try:
                urls = await self._fetch_urls(config, endpoint.id)
            except Exception:
                complete = False
                failures.append(
                    ProviderDiscoveryFailure(
                        external_id=legacy_external_id,
                        error='QuickNode multichain URLs failed.',
                    )
                )
                continue
            endpoint_items: list[DiscoveredEndpoint] = []
            try:
                root_secret = _multichain_secret(endpoint.http_url, urls)
            except ProviderDiscoveryError:
                complete = False
                failures.append(
                    ProviderDiscoveryFailure(
                        external_id=legacy_external_id,
                        error='QuickNode multichain credential path is invalid.',
                    )
                )
                continue
            for network_url in urls:
                pair = network_pairs.get(_normalize_slug(network_url.key)) or _pair_from_key(network_url.key)
                if pair is None:
                    continue
                try:
                    endpoint_items.extend(
                        self._build_items(
                            config.name,
                            endpoint.id,
                            network_url.http_url,
                            pair,
                            network_key=network_url.key,
                            path_secret=root_secret,
                            discover_path_secret=False,
                        )
                    )
                except ProviderDiscoveryError:
                    complete = False
                    failures.append(
                        ProviderDiscoveryFailure(
                            external_id=f'{legacy_external_id}:{network_url.key}',
                            error='QuickNode multichain URL is invalid.',
                        )
                    )
            endpoint_items = [
                replace(item, legacy_external_ids=(legacy_external_id,)) if item.protocol is EndpointProtocol.JSONRPC else item
                for item in endpoint_items
            ]
            items.extend(endpoint_items)
        return ProviderDiscovery(items=items, failures=failures, complete=complete)

    async def _fetch_endpoints(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> list[QuicknodeEndpoint]:
        endpoints: list[QuicknodeEndpoint] = []
        offset = 0
        while True:
            await check_account_active()
            query: dict[str, str | int | bool] = {'limit': 100, 'offset': offset}
            if config.settings.tag_ids:
                query['tag_ids'] = ','.join(str(item) for item in config.settings.tag_ids)
            if config.settings.tag_labels:
                query['tag_labels'] = ','.join(config.settings.tag_labels)
            payload = await get_json(
                self._transport,
                QUICKNODE_ENDPOINTS_URL,
                query=query,
                auth=_admin_auth(config.credential),
            )
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ProviderDiscoveryError('QuickNode API response is invalid.')
            data = payload['data']
            for value in data:
                endpoint = self._parse_endpoint(value)
                if endpoint is not None:
                    endpoints.append(endpoint)
            if len(data) < 100:
                break
            offset += 100
        return endpoints

    async def _fetch_network_pairs(self, config: ProviderDiscoveryConfig) -> dict[str, tuple[Chain, Network]]:
        payload = await get_json(self._transport, QUICKNODE_CHAINS_URL, auth=_admin_auth(config.credential))
        data = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ProviderDiscoveryError('QuickNode chain catalog response is invalid.')
        candidates: dict[str, set[tuple[Chain, Network]]] = {}
        for value in data:
            if not isinstance(value, dict):
                continue
            chain_slug = value.get('slug')
            networks = value.get('networks')
            if not isinstance(chain_slug, str) or not isinstance(networks, list):
                continue
            for network_value in networks:
                if not isinstance(network_value, dict):
                    continue
                network_slug = network_value.get('slug')
                if not isinstance(network_slug, str):
                    continue
                pair = _network_pair(chain_slug, network_slug)
                if pair is None:
                    continue
                keys = {_normalize_slug(network_slug), _normalize_slug(f'{chain_slug}-{network_slug}')}
                for key in keys:
                    candidates.setdefault(key, set()).add(pair)
        return {key: next(iter(pairs)) for key, pairs in candidates.items() if len(pairs) == 1}

    async def _fetch_urls(self, config: ProviderDiscoveryConfig, endpoint_id: str) -> list[QuicknodeNetworkUrl]:
        encoded_id = quote(endpoint_id, safe='')
        payload = await get_json(
            self._transport,
            f'{QUICKNODE_ENDPOINTS_URL}/{encoded_id}/urls',
            auth=_admin_auth(config.credential),
        )
        data = payload.get('data') if isinstance(payload, dict) else None
        multichain_urls = data.get('multichain_urls') if isinstance(data, dict) else None
        if not isinstance(multichain_urls, dict):
            raise ProviderDiscoveryError('QuickNode multichain URL response is invalid.')
        urls: list[QuicknodeNetworkUrl] = []
        for key, value in multichain_urls.items():
            http_url = value.get('http_url') if isinstance(value, dict) else None
            if isinstance(key, str) and key and isinstance(http_url, str) and http_url:
                urls.append(QuicknodeNetworkUrl(key=key, http_url=http_url))
        return urls

    def _build_items(
        self,
        name: str,
        endpoint_id: str,
        http_url: str,
        pair: tuple[Chain, Network],
        *,
        network_key: str | None = None,
        path_secret: str | None = None,
        discover_path_secret: bool = True,
    ) -> list[DiscoveredEndpoint]:
        chain, network = pair
        url, auth_type, auth_secret = _endpoint_connection(
            http_url,
            path_secret=path_secret,
            discover_path_secret=discover_path_secret,
        )
        protocols = [EndpointProtocol.JSONRPC]
        if chain is Chain.TRON:
            protocols.append(EndpointProtocol.HTTP_API)
        items: list[DiscoveredEndpoint] = []
        for protocol in protocols:
            external_id = f'quicknode:{endpoint_id}'
            if network_key is not None:
                external_id = f'{external_id}:{_normalize_slug(network_key)}:{protocol.value}'
            elif protocol is EndpointProtocol.HTTP_API:
                external_id = f'{external_id}:{protocol.value}'
            label = f'{name}-{chain.value}-{network.value}-{protocol.value}-{endpoint_id}'
            items.append(
                DiscoveredEndpoint(
                    external_id=external_id,
                    chain=chain,
                    network=network,
                    protocol=protocol,
                    url=url,
                    auth_type=auth_type,
                    auth_secret=auth_secret,
                    label=label,
                )
            )
        return items

    @staticmethod
    def _parse_endpoint(value: Any) -> QuicknodeEndpoint | None:
        if not isinstance(value, dict):
            return None
        endpoint_id = value.get('id')
        http_url = value.get('http_url')
        chain_slug = value.get('chain')
        network_slug = value.get('network')
        status = value.get('status')
        if not isinstance(endpoint_id, str) or not endpoint_id:
            return None
        if not isinstance(http_url, str) or not http_url:
            return None
        if not isinstance(chain_slug, str) or not chain_slug:
            return None
        if not isinstance(network_slug, str) or not network_slug:
            return None
        if not isinstance(status, str) or not status:
            return None
        return QuicknodeEndpoint(
            id=endpoint_id,
            http_url=http_url,
            chain_slug=chain_slug,
            network_slug=network_slug,
            multichain=value.get('is_multichain') is True,
            status=status,
        )


def _admin_auth(credential: str) -> HttpAuth:
    return HttpAuth(type=EndpointAuthType.HEADER_API_KEY, name='x-api-key', secret=credential)


def _normalize_slug(value: str) -> str:
    return value.strip().casefold().replace('_', '-').replace(' ', '-')


def _network_pair(chain_slug: str, network_slug: str) -> tuple[Chain, Network] | None:
    normalized_chain = _normalize_slug(chain_slug)
    chain = _CHAIN_BY_SLUG.get(normalized_chain)
    if chain is None:
        return None
    normalized_network = _normalize_slug(network_slug)
    chain_aliases = [alias for alias, candidate in _CHAIN_BY_SLUG.items() if candidate is chain]
    for alias in sorted(chain_aliases, key=len, reverse=True):
        prefix = f'{alias}-'
        if normalized_network.startswith(prefix):
            normalized_network = normalized_network.removeprefix(prefix)
            break
    if chain is Chain.SOLANA and normalized_network == 'mainnet':
        normalized_network = Network.MAINNET_BETA.value
    try:
        network = Network(normalized_network)
        validate_chain_network(chain, network)
    except ValueError:
        return None
    return chain, network


def _pair_from_key(value: str) -> tuple[Chain, Network] | None:
    normalized = _normalize_slug(value)
    if normalized in _CHAIN_BY_SLUG:
        return _network_pair(normalized, Network.MAINNET.value)
    for chain_slug in sorted(_CHAIN_BY_SLUG.keys(), key=lambda item: len(item), reverse=True):
        prefix = f'{chain_slug}-'
        if normalized.startswith(prefix):
            return _network_pair(chain_slug, normalized.removeprefix(prefix))
    return None


def _path_secret(url: str) -> str | None:
    parts = urlsplit(url.rstrip('/'))
    segments = [segment for segment in parts.path.split('/') if segment]
    return unquote(segments[-1]) if segments else None


def _multichain_secret(root_url: str, urls: list[QuicknodeNetworkUrl]) -> str | None:
    root_parts = urlsplit(root_url.rstrip('/'))
    root_segments = [unquote(segment) for segment in root_parts.path.split('/') if segment]
    if not root_segments:
        return None
    common_segments = set(root_segments)
    for network_url in urls:
        path = urlsplit(network_url.http_url.rstrip('/')).path
        common_segments.intersection_update(unquote(segment) for segment in path.split('/') if segment)
    network_keys = {_normalize_slug(item.key) for item in urls}
    candidates = [
        segment for segment in root_segments if segment in common_segments and _normalize_slug(segment) not in network_keys
    ]
    if not candidates:
        raise ProviderDiscoveryError('QuickNode multichain credential path is invalid.')
    return candidates[-1]


def _endpoint_connection(
    url: str,
    *,
    path_secret: str | None = None,
    discover_path_secret: bool = True,
) -> tuple[str, EndpointAuthType, str | None]:
    normalized_url = url.rstrip('/')
    parts = urlsplit(normalized_url)
    if path_secret is None and discover_path_secret:
        path_secret = _path_secret(normalized_url)
    if path_secret is None:
        return normalized_url, EndpointAuthType.NONE, None
    segments = parts.path.split('/')
    matches = [index for index, segment in enumerate(segments) if unquote(segment) == path_secret]
    if len(matches) != 1:
        raise ProviderDiscoveryError('QuickNode endpoint credential path is invalid.')
    segments[matches[0]] = PATH_API_KEY_PLACEHOLDER
    path = '/'.join(segments)
    template = urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    return template, EndpointAuthType.PATH_API_KEY, path_secret
