from datetime import UTC, datetime

import pytest
from app.clients.provider import DiscoveredEndpoint, ProviderDiscovery
from app.model.account import AccountStatus
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderVendor
from app.orm.account import Account
from app.orm.application import App
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.http_api_route import HttpApiRoute, HttpApiRouteTarget
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteScope, JsonRpcRouteTarget
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.application import AppProviderManager
from app.services.endpoint.crypto import decrypt_endpoint_url, encrypt_endpoint_url
from app.services.provider import ProviderManager
from app.services.provider.crypto import encrypt_provider_credential
from fastapi import FastAPI


async def _jsonrpc_gateway(app_id: str) -> tuple[Gateway, JsonRpcRoute]:
    gateway = await Gateway.create(
        app_id=app_id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['jsonrpc'],
    )
    route = await JsonRpcRoute.create(gateway_id=gateway.id)
    await JsonRpcRouteScope.create(route_id=route.id, gateway_id=gateway.id, method='')
    return gateway, route


@pytest.mark.anyio
async def test_app_provider_adds_and_removes_only_managed_targets(app: FastAPI) -> None:
    account = await Account.create(email='app-provider@example.com', status=AccountStatus.ACTIVE)
    provider = await Provider.create(
        account_id=account.id,
        name='Alchemy',
        vendor=ProviderVendor.ALCHEMY,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    rpc_app = await App.create(account_id=account.id, name='Provider app')
    _, route = await _jsonrpc_gateway(rpc_app.id)
    manual = await Endpoint.create(
        account_id=account.id,
        name='Manual Ethereum',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url=encrypt_endpoint_url('https://manual.rpc.test'),
    )
    managed = await Endpoint.create(
        account_id=account.id,
        name='Alchemy Ethereum',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        encrypted_url=encrypt_endpoint_url('https://alchemy.rpc.test'),
    )
    await ProviderEndpointBinding.create(
        endpoint_id=managed.id,
        provider_id=provider.id,
        external_id='alchemy:ethereum-mainnet',
        last_seen_at=datetime.now(UTC),
    )
    tron_gateway = await Gateway.create(
        app_id=rpc_app.id,
        name='tron-mainnet',
        chain=Chain.TRON,
        network=Network.MAINNET,
        transport_types=['jsonrpc', 'http_api'],
    )
    http_route = await HttpApiRoute.create(gateway_id=tron_gateway.id)
    tron_http = await Endpoint.create(
        account_id=account.id,
        name='Provider TRON HTTP',
        chain=Chain.TRON,
        network=Network.MAINNET,
        protocol=EndpointProtocol.HTTP_API,
        encrypted_url=encrypt_endpoint_url('https://tron.rpc.test'),
    )
    await ProviderEndpointBinding.create(
        endpoint_id=tron_http.id,
        provider_id=provider.id,
        external_id='provider:tron-mainnet:http-api',
        last_seen_at=datetime.now(UTC),
    )
    await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=manual.id, position=0, weight=50)

    result = await AppProviderManager.set_provider(account.id, rpc_app.id, provider.id)

    assert result.route_targets_added == 2
    await rpc_app.refresh_from_db()
    assert rpc_app.provider_id == provider.id
    targets = await JsonRpcRouteTarget.filter(route_id=route.id).order_by('position')
    assert [(target.endpoint_id, target.source_provider_id, target.weight) for target in targets] == [
        (manual.id, None, 50),
        (managed.id, provider.id, 100),
    ]
    http_targets = await HttpApiRouteTarget.filter(route_id=http_route.id).order_by('position')
    assert [(target.endpoint_id, target.source_provider_id, target.weight) for target in http_targets] == [
        (tron_http.id, provider.id, 100)
    ]
    repeated = await AppProviderManager.set_provider(account.id, rpc_app.id, provider.id)
    assert repeated.route_targets_added == 0

    cleared = await AppProviderManager.clear_provider(account.id, rpc_app.id)

    assert cleared.route_targets_removed == 2
    await rpc_app.refresh_from_db()
    assert rpc_app.provider_id is None
    targets = await JsonRpcRouteTarget.filter(route_id=route.id).order_by('position')
    assert [(target.endpoint_id, target.position) for target in targets] == [(manual.id, 0)]
    assert not await HttpApiRouteTarget.filter(route_id=http_route.id).exists()


@pytest.mark.anyio
async def test_provider_sync_updates_in_place_and_reconciles_app_targets(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await Account.create(email='app-provider-sync@example.com', status=AccountStatus.ACTIVE)
    provider = await Provider.create(
        account_id=account.id,
        name='Alchemy',
        vendor=ProviderVendor.ALCHEMY,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    rpc_app = await App.create(account_id=account.id, provider_id=provider.id, name='Synced provider app')
    _, route = await _jsonrpc_gateway(rpc_app.id)
    inventories = [
        [
            DiscoveredEndpoint(
                external_id='alchemy:a',
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                protocol=EndpointProtocol.JSONRPC,
                url='https://a.rpc.test/v1',
                auth_type=EndpointAuthType.NONE,
                label='Alchemy A',
            )
        ],
        [
            DiscoveredEndpoint(
                external_id='alchemy:a',
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                protocol=EndpointProtocol.JSONRPC,
                url='https://a.rpc.test/v2',
                auth_type=EndpointAuthType.NONE,
                label='Alchemy A',
            ),
            DiscoveredEndpoint(
                external_id='alchemy:b',
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                protocol=EndpointProtocol.JSONRPC,
                url='https://b.rpc.test',
                auth_type=EndpointAuthType.NONE,
                label='Alchemy B',
            ),
        ],
        [
            DiscoveredEndpoint(
                external_id='alchemy:b',
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                protocol=EndpointProtocol.JSONRPC,
                url='https://b.rpc.test',
                auth_type=EndpointAuthType.NONE,
                label='Alchemy B',
            )
        ],
    ]

    class _Adapter:
        async def discover(self, _config: object, _check_account: object) -> ProviderDiscovery:
            return ProviderDiscovery(items=inventories.pop(0))

    monkeypatch.setattr('app.services.provider.sync.build_provider_adapter', lambda _vendor, _transport: _Adapter())
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)

    first = await manager.sync_provider(account.id, provider.id)
    binding_a = await ProviderEndpointBinding.get(external_id='alchemy:a')
    endpoint_a_id = binding_a.endpoint_id
    assert first.route_targets_added == 1

    second = await manager.sync_provider(account.id, provider.id)
    binding_a = await ProviderEndpointBinding.get(external_id='alchemy:a')
    endpoint_a = await Endpoint.get(id=binding_a.endpoint_id)
    assert binding_a.endpoint_id == endpoint_a_id
    assert decrypt_endpoint_url(endpoint_a.encrypted_url) == 'https://a.rpc.test/v2'
    assert second.updated == 1
    assert second.created == 1
    assert second.route_targets_added == 1
    assert await JsonRpcRouteTarget.filter(route_id=route.id).count() == 2

    third = await manager.sync_provider(account.id, provider.id)
    endpoint_a = await Endpoint.get(id=endpoint_a_id)
    assert third.archived == 1
    assert third.route_targets_removed == 1
    assert endpoint_a.deleted_at is not None
    targets = await JsonRpcRouteTarget.filter(route_id=route.id).order_by('position')
    assert len(targets) == 1
    assert targets[0].source_provider_id == provider.id
    assert targets[0].position == 0
