from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointAuditAction, EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderVendor
from app.orm.account import Account
from app.orm.application import App
from app.orm.endpoint import Endpoint, EndpointAuditEvent
from app.orm.gateway import Gateway
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteTarget
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.endpoint import EndpointManager, build_endpoint_connection
from app.services.endpoint.crypto import encrypt_endpoint_secret, encrypt_endpoint_url
from app.services.jsonrpc_route import DatabaseJsonRpcEndpointRouteReferenceLookup
from app.services.provider import ProviderManager
from app.services.provider.crypto import encrypt_provider_credential
from fastapi import FastAPI


@dataclass(frozen=True, slots=True)
class _ProviderInventory:
    account: Account
    provider: Provider
    referenced: Endpoint
    unreferenced: Endpoint


async def _create_inventory(*, add_route: bool) -> _ProviderInventory:
    account = await Account.create(email='provider-delete@example.com')
    provider = await Provider.create(
        account_id=account.id,
        name='Provider to delete',
        vendor=ProviderVendor.ALCHEMY,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
    )
    endpoints: list[Endpoint] = []
    for name in ('referenced', 'unreferenced'):
        endpoint = await Endpoint.create(
            account_id=account.id,
            name=name,
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            protocol=EndpointProtocol.JSONRPC,
            encrypted_url=encrypt_endpoint_url(f'https://{name}.example.com/rpc'),
            auth_type=EndpointAuthType.BEARER,
            encrypted_auth_secret=encrypt_endpoint_secret(f'{name}-secret'),
        )
        await ProviderEndpointBinding.create(
            endpoint_id=endpoint.id,
            provider_id=provider.id,
            external_id=f'alchemy:{name}',
            last_seen_at=datetime.now(UTC),
        )
        endpoints.append(endpoint)

    referenced, unreferenced = endpoints
    if add_route:
        app = await App.create(account_id=account.id, name='Provider delete app')
        gateway = await Gateway.create(
            app_id=app.id,
            name='ethereum-mainnet',
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            transport_types=['jsonrpc'],
        )
        route = await JsonRpcRoute.create(gateway_id=gateway.id)
        await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=referenced.id, position=0, weight=100)
    return _ProviderInventory(account=account, provider=provider, referenced=referenced, unreferenced=unreferenced)


@pytest.mark.anyio
async def test_delete_provider_retains_and_detaches_all_endpoints(app: FastAPI) -> None:
    inventory = await _create_inventory(add_route=False)
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)
    result = await manager.delete_provider(inventory.account.id, inventory.provider.id)

    assert result.archived_endpoints == 0
    assert result.retained_endpoints == 2
    assert result.detached_endpoints == 2
    assert await ProviderEndpointBinding.filter(provider_id=inventory.provider.id).count() == 0

    await inventory.provider.refresh_from_db()
    assert inventory.provider.deleted_at is not None
    for endpoint in (inventory.referenced, inventory.unreferenced):
        await endpoint.refresh_from_db()
        assert endpoint.deleted_at is None
        assert endpoint.version == 2
        event = await EndpointAuditEvent.get(endpoint_id=endpoint.id)
        assert event.action == EndpointAuditAction.UPDATED
        assert event.changed_fields == ['provider']

    endpoint_manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())
    detail = await endpoint_manager.get_endpoint(inventory.account.id, inventory.referenced.id)
    assert detail.origin_type == 'manual'
    assert detail.provider is None
    assert detail.configured_url == 'https://referenced.example.com/rpc'
    assert detail.auth.model_dump() == {
        'type': EndpointAuthType.BEARER,
        'has_secret': True,
        'secret': 'referenced-secret',
    }
    connection = build_endpoint_connection(inventory.referenced)
    assert connection.url == 'https://referenced.example.com/rpc'
    assert connection.auth.type is EndpointAuthType.BEARER
    assert connection.auth.secret == 'referenced-secret'


@pytest.mark.anyio
async def test_delete_provider_only_archives_unreferenced_endpoints(app: FastAPI) -> None:
    inventory = await _create_inventory(add_route=True)
    manager = app.state.provider_manager
    assert isinstance(manager, ProviderManager)
    result = await manager.delete_provider(
        inventory.account.id,
        inventory.provider.id,
        delete_unreferenced_endpoints=True,
    )

    assert result.archived_endpoints == 1
    assert result.retained_endpoints == 1
    assert result.detached_endpoints == 2
    assert await ProviderEndpointBinding.filter(provider_id=inventory.provider.id).count() == 0

    await inventory.referenced.refresh_from_db()
    await inventory.unreferenced.refresh_from_db()
    assert inventory.referenced.deleted_at is None
    assert inventory.unreferenced.deleted_at is not None
    referenced_event = await EndpointAuditEvent.get(endpoint_id=inventory.referenced.id)
    archived_event = await EndpointAuditEvent.get(endpoint_id=inventory.unreferenced.id)
    assert referenced_event.action == EndpointAuditAction.UPDATED
    assert referenced_event.changed_fields == ['provider']
    assert archived_event.action == EndpointAuditAction.ARCHIVED

    endpoint_manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())
    detail = await endpoint_manager.get_endpoint(inventory.account.id, inventory.referenced.id)
    assert detail.origin_type == 'manual'
    assert detail.configured_url == 'https://referenced.example.com/rpc'
    assert detail.auth.model_dump() == {
        'type': EndpointAuthType.BEARER,
        'has_secret': True,
        'secret': 'referenced-secret',
    }
    connection = build_endpoint_connection(inventory.referenced)
    assert connection.url == 'https://referenced.example.com/rpc'
    assert connection.auth.type is EndpointAuthType.BEARER
    assert connection.auth.secret == 'referenced-secret'
