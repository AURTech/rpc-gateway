import httpx
import pytest
from app.clients.provider import ProviderDiscoveryConfig, ProviderDiscoveryError
from app.clients.provider.alchemy import AlchemyProviderAdapter
from app.clients.provider.chainstack import ChainstackProviderAdapter
from app.clients.provider.drpc import DrpcProviderAdapter
from app.clients.provider.probe import probe_evm_endpoints
from app.clients.provider.quicknode import QuicknodeProviderAdapter
from app.clients.provider.tenderly import TenderlyProviderAdapter
from app.clients.transport import HttpAuth, HttpTransport
from app.infra.outbound_policy import OutboundTargetPolicy
from app.model.provider import ProviderSettingsParams


async def _account_is_active() -> None:
    return None


@pytest.mark.anyio
async def test_chainstack_rejects_cross_origin_pagination_before_sending_credential() -> None:
    requests: list[httpx.Request] = []

    async def send(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'results': [], 'next': 'https://attacker.example.test/nodes'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = ChainstackProviderAdapter(HttpTransport(client))
        config = ProviderDiscoveryConfig(
            credential='provider-secret',
            settings=ProviderSettingsParams(),
        )
        with pytest.raises(ProviderDiscoveryError, match='pagination URL'):
            await adapter.discover(config, _account_is_active)

    assert len(requests) == 1
    assert requests[0].url.host == 'api.chainstack.com'
    assert requests[0].headers['authorization'] == 'Bearer provider-secret'


@pytest.mark.anyio
async def test_alchemy_builds_all_supported_catalog_protocols() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'eth-mainnet.g.alchemy.com':
            assert request.url.path == '/v2/provider-secret'
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': '0x1'})
        assert request.url == 'https://app-api.alchemy.com/trpc/config.getNetworkConfig'
        return httpx.Response(200, json={'result': {'data': []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = AlchemyProviderAdapter(HttpTransport(client))
        discovery = await adapter.discover(
            ProviderDiscoveryConfig(
                credential='provider-secret',
                settings=ProviderSettingsParams(),
            ),
            _account_is_active,
        )

    discovered = {(item.chain.value, item.network.value, item.protocol.value) for item in discovery.items}
    assert ('solana', 'mainnet-beta', 'jsonrpc') in discovered
    assert ('bitcoin', 'testnet', 'jsonrpc') in discovered
    assert ('litecoin', 'testnet', 'jsonrpc') in discovered
    assert ('tron', 'mainnet', 'jsonrpc') in discovered
    assert ('tron', 'mainnet', 'http_api') in discovered
    assert ('tron', 'nile', 'http_api') in discovered
    assert len(discovered) == 22


@pytest.mark.anyio
async def test_drpc_maps_supported_non_evm_networks_without_chain_ids() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'lb.drpc.live':
            assert request.url.path == '/ethereum/provider-secret'
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': '0x1'})
        return httpx.Response(
            200,
            json=[
                {
                    'chains': [
                        {
                            'name': 'solana-devnet',
                            'api_type': 'jsonrpc',
                            'blockchain_type': 'solana',
                            'priority': 10,
                        },
                        {
                            'name': 'bitcoin',
                            'api_type': 'jsonrpc',
                            'blockchain_type': 'bitcoin',
                            'priority': 100,
                        },
                        {
                            'name': 'tron',
                            'chain_id': '0x2b6653dc',
                            'api_type': 'jsonrpc',
                            'blockchain_type': 'eth',
                            'priority': 100,
                        },
                        {
                            'name': 'litecoin',
                            'api_type': 'jsonrpc',
                            'blockchain_type': 'bitcoin',
                            'priority': 100,
                        },
                    ]
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = DrpcProviderAdapter(HttpTransport(client))
        discovery = await adapter.discover(
            ProviderDiscoveryConfig(credential='provider-secret', settings=ProviderSettingsParams()),
            _account_is_active,
        )

    assert [(item.chain.value, item.network.value) for item in discovery.items] == [
        ('bitcoin', 'mainnet'),
        ('solana', 'devnet'),
        ('tron', 'mainnet'),
    ]
    assert all(item.protocol.value == 'jsonrpc' for item in discovery.items)
    assert all(item.auth_type.value == 'path_api_key' for item in discovery.items)
    assert all(item.auth_secret == 'provider-secret' for item in discovery.items)
    assert [item.url for item in discovery.items] == [
        'https://lb.drpc.live/bitcoin/{api_key}',
        'https://lb.drpc.live/solana-devnet/{api_key}',
        'https://lb.drpc.live/tron/{api_key}',
    ]


@pytest.mark.anyio
async def test_drpc_extracts_key_from_standard_endpoint_url() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'lb.drpc.live':
            assert request.url.path == '/ethereum/endpoint-secret'
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': '0x1'})
        return httpx.Response(
            200,
            json=[
                {
                    'chains': [
                        {
                            'name': 'solana',
                            'api_type': 'jsonrpc',
                            'blockchain_type': 'solana',
                        }
                    ]
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = DrpcProviderAdapter(HttpTransport(client))
        discovery = await adapter.discover(
            ProviderDiscoveryConfig(
                credential='https://lb.drpc.live/ethereum/endpoint-secret',
                settings=ProviderSettingsParams(),
            ),
            _account_is_active,
        )

    assert len(discovery.items) == 1
    assert discovery.items[0].url == 'https://lb.drpc.live/solana/{api_key}'
    assert discovery.items[0].auth_type.value == 'path_api_key'
    assert discovery.items[0].auth_secret == 'endpoint-secret'


@pytest.mark.anyio
@pytest.mark.parametrize(
    'credential',
    [
        '',
        'bad/key',
        'http://lb.drpc.live/ethereum/endpoint-secret',
        'https://attacker.example/ethereum/endpoint-secret',
        'https://lb.drpc.live/ethereum',
        'https://lb.drpc.live/unknown/endpoint-secret',
        'https://lb.drpc.live/ethereum/endpoint-secret?mode=test',
    ],
)
async def test_drpc_rejects_invalid_credentials_before_network_request(credential: str) -> None:
    requested = False

    async def send(_request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = DrpcProviderAdapter(HttpTransport(client))
        with pytest.raises(ProviderDiscoveryError, match='dRPC'):
            await adapter.discover(
                ProviderDiscoveryConfig(credential=credential, settings=ProviderSettingsParams()),
                _account_is_active,
            )

    assert requested is False


@pytest.mark.anyio
async def test_chainstack_joins_v1_credentials_with_v2_network_metadata() -> None:
    requests: list[httpx.Request] = []

    async def send(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer provider-secret'
        if request.url.path == '/v1/nodes/':
            assert request.url.params['project'] == 'project-1'
            return httpx.Response(
                200,
                json={
                    'results': [
                        {
                            'id': 'solana-1',
                            'status': 'running',
                            'details': {'https_endpoint': 'https://solana.p2pify.com', 'auth_key': 'solana-secret'},
                        },
                        {
                            'id': 'tron-1',
                            'status': 'running',
                            'details': {'https_endpoint': 'https://tron.p2pify.com/tron-secret'},
                        },
                        {
                            'id': 'litecoin-1',
                            'status': 'running',
                            'details': {'https_endpoint': 'https://litecoin.p2pify.com'},
                        },
                    ],
                    'next': None,
                },
            )
        if request.url.path == '/v2/nodes/':
            assert 'project' not in request.url.params
            return httpx.Response(
                200,
                json={
                    'results': [
                        {'id': 'solana-1', 'protocol': 'solana', 'network': 'solana-mainnet'},
                        {'id': 'tron-1', 'protocol': 'tron', 'network': 'tron-nile-testnet'},
                        {'id': 'litecoin-1', 'protocol': 'litecoin', 'network': 'litecoin-mainnet'},
                    ],
                    'next': None,
                },
            )
        raise AssertionError(f'Unexpected request path: {request.url.path}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = ChainstackProviderAdapter(HttpTransport(client))
        discovery = await adapter.discover(
            ProviderDiscoveryConfig(
                credential='provider-secret',
                settings=ProviderSettingsParams(project='project-1'),
            ),
            _account_is_active,
        )

    assert [(item.chain.value, item.network.value, item.protocol.value) for item in discovery.items] == [
        ('solana', 'mainnet-beta', 'jsonrpc'),
        ('tron', 'nile', 'http_api'),
        ('tron', 'nile', 'jsonrpc'),
        ('litecoin', 'mainnet', 'jsonrpc'),
    ]
    assert discovery.items[1].auth_secret == 'tron-secret'
    assert discovery.items[1].url == 'https://tron.p2pify.com'
    assert len(requests) == 2


@pytest.mark.anyio
async def test_tenderly_filters_node_rpc_catalog_through_capabilities() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'mainnet.gateway.tenderly.co':
            assert request.url.path == '/provider-secret'
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': '0x1'})
        return httpx.Response(
            200,
            json=[
                {
                    'chain_id': '1',
                    'network_slugs': {'node_rpc_slug': 'mainnet'},
                    'supported_features': {'node': True},
                },
                {
                    'chain_id': '56',
                    'network_slugs': {'node_rpc_slug': 'bnb'},
                    'supported_features': {'node': True},
                },
                {
                    'chain_id': '10',
                    'network_slugs': {'node_rpc_slug': 'optimism'},
                    'supported_features': {'node': False},
                },
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = TenderlyProviderAdapter(HttpTransport(client))
        discovery = await adapter.discover(
            ProviderDiscoveryConfig(credential='provider-secret', settings=ProviderSettingsParams()),
            _account_is_active,
        )

    assert len(discovery.items) == 1
    assert discovery.items[0].chain.value == 'ethereum'


@pytest.mark.anyio
async def test_alchemy_rejects_invalid_provider_credential() -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        assert request.url.host == 'eth-mainnet.g.alchemy.com'
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32600}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = AlchemyProviderAdapter(HttpTransport(client))
        with pytest.raises(ProviderDiscoveryError, match='credential validation failed'):
            await adapter.discover(
                ProviderDiscoveryConfig(credential='invalid', settings=ProviderSettingsParams()),
                _account_is_active,
            )


@pytest.mark.anyio
async def test_probe_rejects_private_target_before_transport_request(monkeypatch: pytest.MonkeyPatch) -> None:
    requested = False

    async def send(_request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': '0x1'})

    monkeypatch.setattr(
        'app.clients.provider.probe.build_outbound_target_policy',
        lambda: OutboundTargetPolicy(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        pairs, failures = await probe_evm_endpoints(
            HttpTransport(client),
            [('private', 'http://127.0.0.1/rpc', HttpAuth())],
            _account_is_active,
        )

    assert pairs == {}
    assert len(failures) == 1
    assert failures[0].external_id == 'private'
    assert requested is False


@pytest.mark.anyio
async def test_quicknode_expands_supported_multichain_urls_without_health_probes() -> None:
    requests: list[httpx.Request] = []

    async def send(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers['x-api-key'] == 'admin-secret'
        if request.url.path == '/v0/endpoints':
            return httpx.Response(
                200,
                json={
                    'data': [
                        {
                            'id': 'multi-1',
                            'http_url': 'https://multi.quiknode.pro/root-secret/ethereum-mainnet/',
                            'chain': 'ethereum',
                            'network': 'mainnet',
                            'status': 'active',
                            'is_multichain': True,
                        }
                    ]
                },
            )
        if request.url.path == '/v0/chains':
            return httpx.Response(
                200,
                json={
                    'data': [
                        {'slug': 'ethereum', 'networks': [{'slug': 'ethereum-mainnet'}]},
                        {'slug': 'solana', 'networks': [{'slug': 'solana-mainnet'}]},
                        {'slug': 'bitcoin', 'networks': [{'slug': 'bitcoin-testnet'}]},
                        {'slug': 'litecoin', 'networks': [{'slug': 'litecoin-mainnet'}]},
                        {'slug': 'polygon', 'networks': [{'slug': 'polygon-mainnet'}, {'slug': 'polygon-amoy'}]},
                        {'slug': 'tron', 'networks': [{'slug': 'tron-mainnet'}]},
                    ]
                },
            )
        if request.url.path == '/v0/endpoints/multi-1/urls':
            return httpx.Response(
                200,
                json={
                    'data': {
                        'multichain_urls': {
                            'ethereum-mainnet': {'http_url': 'https://multi.quiknode.pro/root-secret/ethereum-mainnet/'},
                            'solana-mainnet': {'http_url': 'https://multi.quiknode.pro/root-secret/solana-mainnet/'},
                            'bitcoin-testnet': {'http_url': 'https://multi.quiknode.pro/root-secret/bitcoin-testnet/'},
                            'litecoin-mainnet': {'http_url': 'https://multi.quiknode.pro/root-secret/litecoin-mainnet/'},
                            'polygon': {'http_url': 'https://multi.quiknode.pro/root-secret/polygon/'},
                            'polygon-amoy': {'http_url': 'https://multi.quiknode.pro/root-secret/polygon-amoy/'},
                            'tron-mainnet': {'http_url': 'https://multi.quiknode.pro/root-secret/tron-mainnet/'},
                            'avalanche-mainnet': {'http_url': 'https://multi.quiknode.pro/root-secret/avalanche-mainnet/'},
                        }
                    }
                },
            )
        raise AssertionError(f'Unexpected request path: {request.url.path}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        adapter = QuicknodeProviderAdapter(HttpTransport(client))
        discovery = await adapter.discover(
            ProviderDiscoveryConfig(
                credential='admin-secret',
                settings=ProviderSettingsParams(),
            ),
            _account_is_active,
        )

    assert discovery.complete is True
    assert discovery.failures == []
    assert [(item.chain.value, item.network.value, item.protocol.value) for item in discovery.items] == [
        ('ethereum', 'mainnet', 'jsonrpc'),
        ('solana', 'mainnet-beta', 'jsonrpc'),
        ('bitcoin', 'testnet', 'jsonrpc'),
        ('litecoin', 'mainnet', 'jsonrpc'),
        ('polygon', 'mainnet', 'jsonrpc'),
        ('polygon', 'amoy', 'jsonrpc'),
        ('tron', 'mainnet', 'jsonrpc'),
        ('tron', 'mainnet', 'http_api'),
    ]
    assert discovery.items[0].legacy_external_ids == ('quicknode:multi-1',)
    assert discovery.items[1].legacy_external_ids == ('quicknode:multi-1',)
    assert all(item.legacy_external_ids == ('quicknode:multi-1',) for item in discovery.items[:-1])
    assert discovery.items[-1].legacy_external_ids == ()
    assert all(item.auth_secret == 'root-secret' for item in discovery.items)
    assert discovery.items[0].url == 'https://multi.quiknode.pro/{api_key}/ethereum-mainnet'
    assert discovery.items[1].url == 'https://multi.quiknode.pro/{api_key}/solana-mainnet'
    assert len(requests) == 3
