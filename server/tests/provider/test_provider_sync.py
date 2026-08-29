from datetime import UTC, datetime

import pytest
from app.clients.provider import DiscoveredEndpoint, ProviderDiscovery
from app.model.account import AccountStatus
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderEndpointAction, ProviderEndpointDiscoveryStatus, ProviderVendor
from app.orm.account import Account
from app.orm.application import App
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteTarget
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.endpoint import EndpointManager
from app.services.endpoint.crypto import (
    decrypt_endpoint_secret,
    decrypt_endpoint_url,
    encrypt_endpoint_secret,
    encrypt_endpoint_url,
)
from app.services.endpoint.transport import build_endpoint_url
from app.services.jsonrpc_route import DatabaseJsonRpcEndpointRouteReferenceLookup
from app.services.provider import ProviderManager
from app.services.provider.crypto import encrypt_provider_credential
from app.services.provider.sync import _endpoint_name
from fastapi import FastAPI


def test_generated_endpoint_name_is_short_and_omits_default_protocol() -> None:
    endpoint = DiscoveredEndpoint(
        external_id='alchemy:1',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        url='https://eth-mainnet.example.test',
    )

    assert _endpoint_name('Alchemy', endpoint) == 'Alchemy · ethereum-mainnet'


def test_generated_endpoint_name_truncates_provider_and_includes_http_api() -> None:
    endpoint = DiscoveredEndpoint(
        external_id='quicknode:tron:http_api',
        chain=Chain.TRON,
        network=Network.MAINNET,
        protocol=EndpointProtocol.HTTP_API,
        url='https://tron-mainnet.example.test',
    )

    assert _endpoint_name('Provider configuration with a long name', endpoint) == (
        'Provider configuration… · tron-mainnet · HTTP API'
    )


@pytest.mark.anyio
async def test_sync_migrates_legacy_quicknode_binding_in_place(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    account = await Account.create(email='quicknode-sync@example.com', status=AccountStatus.ACTIVE)
    provider = await Provider.create(
        account_id=account.id,
        name='QuickNode',
        vendor=ProviderVendor.QUICKNODE,
        encrypted_credential=encrypt_provider_credential('admin-secret'),
    )
    endpoint = await Endpoint.create(
        account_id=account.id,
        name='QuickNode Ethereum',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url=encrypt_endpoint_url('https://legacy.quiknode.pro'),
        auth_type=EndpointAuthType.PATH_API_KEY,
        encrypted_auth_secret=encrypt_endpoint_secret('legacy-secret'),
    )
    await ProviderEndpointBinding.create(
        endpoint_id=endpoint.id,
        provider_id=provider.id,
        external_id='quicknode:multi-1',
        last_seen_at=datetime.now(UTC),
    )
    rpc_app = await App.create(account_id=account.id, name='QuickNode route app')
    gateway = await Gateway.create(
        app_id=rpc_app.id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['jsonrpc'],
    )
    route = await JsonRpcRoute.create(gateway_id=gateway.id)
    route_target = await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=endpoint.id, position=0, weight=100)

    class _Adapter:
        async def discover(self, _config: object, _check_account: object) -> ProviderDiscovery:
            return ProviderDiscovery(
                items=[
                    DiscoveredEndpoint(
                        external_id='quicknode:multi-1:solana-mainnet:jsonrpc',
                        legacy_external_ids=('quicknode:multi-1',),
                        chain=Chain.SOLANA,
                        network=Network.MAINNET_BETA,
                        protocol=EndpointProtocol.JSONRPC,
                        url='https://multi.quiknode.pro/{api_key}/solana-mainnet',
                        auth_type=EndpointAuthType.PATH_API_KEY,
                        auth_secret='root-secret',
                    ),
                    DiscoveredEndpoint(
                        external_id='quicknode:multi-1:ethereum-mainnet:jsonrpc',
                        legacy_external_ids=('quicknode:multi-1',),
                        chain=Chain.ETHEREUM,
                        network=Network.MAINNET,
                        protocol=EndpointProtocol.JSONRPC,
                        url='https://multi.quiknode.pro/{api_key}/ethereum-mainnet',
                        auth_type=EndpointAuthType.PATH_API_KEY,
                        auth_secret='root-secret',
                    ),
                ]
            )

    monkeypatch.setattr('app.services.provider.sync.build_provider_adapter', lambda _vendor, _transport: _Adapter())
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    result = await manager.sync_provider(account.id, provider.id)

    assert result.status == 'success'
    assert result.created == 1
    assert result.updated == 1
    assert [item.action for item in result.items] == [ProviderEndpointAction.CREATED, ProviderEndpointAction.UPDATED]
    created = await Endpoint.get(account_id=account.id, name='QuickNode · solana-mainnet-beta')
    assert created.protocol == EndpointProtocol.JSONRPC
    binding = await ProviderEndpointBinding.get(endpoint_id=endpoint.id)
    assert binding.endpoint_id == endpoint.id
    assert binding.external_id == 'quicknode:multi-1:ethereum-mainnet:jsonrpc'
    await route_target.refresh_from_db()
    assert route_target.endpoint_id == endpoint.id
    await endpoint.refresh_from_db()
    assert endpoint.id == binding.endpoint_id
    assert endpoint.version == 2


@pytest.mark.anyio
async def test_sync_migrates_drpc_query_auth_to_path_auth_in_place(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='drpc-sync@example.com', status=AccountStatus.ACTIVE)
    provider = await Provider.create(
        account_id=account.id,
        name='dRPC',
        vendor=ProviderVendor.DRPC,
        encrypted_credential=encrypt_provider_credential('endpoint-secret'),
    )
    endpoint = await Endpoint.create(
        account_id=account.id,
        name='dRPC Ethereum',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url=encrypt_endpoint_url('https://lb.drpc.org/ogrpc?network=ethereum'),
        auth_type=EndpointAuthType.QUERY_API_KEY,
        auth_query_param='dkey',
        encrypted_auth_secret=encrypt_endpoint_secret('endpoint-secret'),
    )
    await ProviderEndpointBinding.create(
        endpoint_id=endpoint.id,
        provider_id=provider.id,
        external_id='drpc:1:ethereum',
        last_seen_at=datetime.now(UTC),
    )
    rpc_app = await App.create(account_id=account.id, name='dRPC route app')
    gateway = await Gateway.create(
        app_id=rpc_app.id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['jsonrpc'],
    )
    route = await JsonRpcRoute.create(gateway_id=gateway.id)
    route_target = await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=endpoint.id, position=0, weight=100)

    class _Adapter:
        async def discover(self, _config: object, _check_account: object) -> ProviderDiscovery:
            return ProviderDiscovery(
                items=[
                    DiscoveredEndpoint(
                        external_id='drpc:1:ethereum',
                        chain=Chain.ETHEREUM,
                        network=Network.MAINNET,
                        protocol=EndpointProtocol.JSONRPC,
                        url='https://lb.drpc.live/ethereum/{api_key}',
                        auth_type=EndpointAuthType.PATH_API_KEY,
                        auth_secret='endpoint-secret',
                    )
                ]
            )

    monkeypatch.setattr('app.services.provider.sync.build_provider_adapter', lambda _vendor, _transport: _Adapter())
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    result = await manager.sync_provider(account.id, provider.id)

    assert result.status == 'success'
    assert result.updated == 1
    assert result.items[0].action is ProviderEndpointAction.UPDATED
    await route_target.refresh_from_db()
    assert route_target.endpoint_id == endpoint.id
    await endpoint.refresh_from_db()
    assert endpoint.version == 2
    assert endpoint.auth_type == EndpointAuthType.PATH_API_KEY
    assert endpoint.auth_query_param is None
    assert decrypt_endpoint_url(endpoint.encrypted_url) == 'https://lb.drpc.live/ethereum/{api_key}'
    assert decrypt_endpoint_secret(endpoint.encrypted_auth_secret or '') == 'endpoint-secret'
    assert build_endpoint_url(endpoint) == 'https://lb.drpc.live/ethereum/endpoint-secret'


@pytest.mark.anyio
async def test_incomplete_discovery_does_not_archive_missing_endpoints(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='partial-provider-sync@example.com', status=AccountStatus.ACTIVE)
    provider = await Provider.create(
        account_id=account.id,
        name='Alchemy',
        vendor=ProviderVendor.ALCHEMY,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    endpoint = await Endpoint.create(
        account_id=account.id,
        name='Alchemy Ethereum',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url=encrypt_endpoint_url('https://eth-mainnet.g.alchemy.com/v2'),
        auth_type=EndpointAuthType.PATH_API_KEY,
        encrypted_auth_secret=encrypt_endpoint_secret('provider-secret'),
    )
    await ProviderEndpointBinding.create(
        endpoint_id=endpoint.id,
        provider_id=provider.id,
        external_id='alchemy:1',
        last_seen_at=datetime.now(UTC),
    )

    class _Adapter:
        async def discover(self, _config: object, _check_account: object) -> ProviderDiscovery:
            return ProviderDiscovery(items=[], complete=False)

    monkeypatch.setattr('app.services.provider.sync.build_provider_adapter', lambda _vendor, _transport: _Adapter())
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    result = await manager.sync_provider(account.id, provider.id)

    assert result.status == 'partial'
    assert result.archived == 0
    await endpoint.refresh_from_db()
    assert endpoint.deleted_at is None
    binding = await ProviderEndpointBinding.get(endpoint_id=endpoint.id)
    assert binding.discovery_status == 'present'
    assert binding.missing_since is None


@pytest.mark.anyio
async def test_complete_discovery_marks_routed_missing_endpoint_as_retained(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='retained-provider-sync@example.com', status=AccountStatus.ACTIVE)
    provider = await Provider.create(
        account_id=account.id,
        name='Retained Alchemy',
        vendor=ProviderVendor.ALCHEMY,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    endpoint = await Endpoint.create(
        account_id=account.id,
        name='Retained Ethereum',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url=encrypt_endpoint_url('https://eth-mainnet.g.alchemy.com/v2'),
        auth_type=EndpointAuthType.PATH_API_KEY,
        encrypted_auth_secret=encrypt_endpoint_secret('provider-secret'),
    )
    await ProviderEndpointBinding.create(
        endpoint_id=endpoint.id,
        provider_id=provider.id,
        external_id='alchemy:retained',
        last_seen_at=datetime.now(UTC),
    )
    rpc_app = await App.create(account_id=account.id, name='Retained route app')
    gateway = await Gateway.create(
        app_id=rpc_app.id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['jsonrpc'],
    )
    route = await JsonRpcRoute.create(gateway_id=gateway.id)
    await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=endpoint.id, position=0, weight=100)

    class _Adapter:
        async def discover(self, _config: object, _check_account: object) -> ProviderDiscovery:
            return ProviderDiscovery(items=[], complete=True)

    monkeypatch.setattr('app.services.provider.sync.build_provider_adapter', lambda _vendor, _transport: _Adapter())
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    result = await manager.sync_provider(account.id, provider.id)
    inventory = await manager.list_provider_endpoints(
        account.id,
        provider.id,
        discovery_status=ProviderEndpointDiscoveryStatus.MISSING,
        retained_by_routes=True,
    )

    assert result.status == 'partial'
    assert result.archived == 0
    await endpoint.refresh_from_db()
    assert endpoint.deleted_at is None
    binding = await ProviderEndpointBinding.get(endpoint_id=endpoint.id)
    assert binding.discovery_status == 'missing'
    assert binding.missing_since is not None
    assert inventory.total == 1
    assert inventory.items[0].registry_state == 'active'
    assert inventory.items[0].retained_by_routes is True
    endpoint_manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())
    detail = await endpoint_manager.get_endpoint(account.id, endpoint.id)
    assert detail.url == 'https://eth-mainnet.g.alchemy.com/v2'
    assert detail.auth.model_dump() == {'type': EndpointAuthType.PATH_API_KEY, 'has_secret': True}
