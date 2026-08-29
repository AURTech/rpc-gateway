from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from app.core.errors import BadRequestError, NotfoundError
from app.model.blockchain import Chain, Network
from app.model.endpoint import (
    BulkDeleteEndpointParams,
    EndpointAuthType,
    EndpointNoAuthCreateParams,
    EndpointProtocol,
    ManagedEndpointParams,
    ManagedEndpointReferencedError,
    ManagedEndpointValidationError,
)
from app.orm.account import Account
from app.orm.application import App
from app.orm.endpoint import Endpoint, EndpointAuditEvent
from app.orm.gateway import Gateway
from app.orm.http_api_route import HttpApiRoute, HttpApiRouteTarget
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteTarget
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.application import ApplicationManager
from app.services.endpoint import EndpointManager, ManagedEndpointManager
from app.services.http_api_route import DatabaseEndpointRouteReferenceLookup
from app.services.jsonrpc_route import DatabaseJsonRpcEndpointRouteReferenceLookup
from tortoise.context import tortoise_test_context
from tortoise.transactions import in_transaction


@pytest.fixture
async def route_schema() -> AsyncGenerator[None]:
    async with tortoise_test_context(['app.orm'], connection_label='endpoint_route_reference'):
        yield


async def _create_endpoint(
    endpoint_id: str,
    protocol: EndpointProtocol = EndpointProtocol.JSONRPC,
) -> Endpoint:
    account, _created = await Account.get_or_create(id='account00000000000001', defaults={'email': 'route@example.com'})
    return await Endpoint.create(
        id=endpoint_id,
        account_id=account.id,
        name=endpoint_id,
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=protocol,
        encrypted_url='encrypted-url',
        enabled=True,
        auth_type=EndpointAuthType.NONE,
        version=1,
    )


async def _create_route(endpoint_id: str) -> JsonRpcRoute:
    account = await Account.get(id='account00000000000001')
    app = await App.create(id='app000000000000000001', account_id=account.id, name='Route app')
    gateway = await Gateway.create(
        id='gateway00000000000001',
        app_id=app.id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['jsonrpc'],
    )
    route = await JsonRpcRoute.create(id='route0000000000000001', gateway_id=gateway.id)
    await JsonRpcRouteTarget.create(route_id=route.id, endpoint_id=endpoint_id, position=0, weight=100)
    return route


@pytest.mark.anyio
async def test_reference_lookup_only_returns_active_route_targets(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    route = await _create_route(endpoint.id)
    lookup = DatabaseJsonRpcEndpointRouteReferenceLookup()
    deleted_at = datetime.now(UTC)

    async with in_transaction() as connection:
        referenced = await lookup.referenced_endpoint_ids([endpoint.id, 'missing'], using_db=connection)

    assert referenced == {endpoint.id}

    await JsonRpcRoute.filter(id=route.id).update(deleted_at=deleted_at)
    async with in_transaction() as connection:
        referenced = await lookup.referenced_endpoint_ids([endpoint.id], using_db=connection)

    assert referenced == set()

    await JsonRpcRoute.filter(id=route.id).update(deleted_at=None)
    await Gateway.filter(id=route.gateway_id).update(deleted_at=deleted_at)
    async with in_transaction() as connection:
        referenced = await lookup.referenced_endpoint_ids([endpoint.id], using_db=connection)

    assert referenced == set()

    await Gateway.filter(id=route.gateway_id).update(deleted_at=None)
    await App.filter(id='app000000000000000001').update(deleted_at=deleted_at)
    async with in_transaction() as connection:
        referenced = await lookup.referenced_endpoint_ids([endpoint.id], using_db=connection)

    assert referenced == set()


@pytest.mark.anyio
async def test_manual_delete_removes_referenced_endpoint_from_route(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    await _create_route(endpoint.id)
    manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    await manager.delete_endpoint(endpoint.account_id, endpoint.account_id, endpoint.id)

    await endpoint.refresh_from_db()
    assert endpoint.deleted_at is not None
    assert endpoint.version == 2
    assert await JsonRpcRouteTarget.filter(endpoint_id=endpoint.id).count() == 0
    assert await EndpointAuditEvent.filter(endpoint_id=endpoint.id).count() == 1


@pytest.mark.anyio
async def test_bulk_delete_removes_references_and_deletes_all_endpoints(route_schema: None) -> None:
    referenced = await _create_endpoint('endpoint0000000000001')
    deletable = await _create_endpoint('endpoint0000000000002')
    await _create_route(referenced.id)
    manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    result = await manager.bulk_delete_endpoints(
        referenced.account_id,
        referenced.account_id,
        BulkDeleteEndpointParams(endpoint_ids=[deletable.id, referenced.id]),
    )

    assert result.total == 2
    assert [item.id for item in result.deleted] == [deletable.id, referenced.id]
    await referenced.refresh_from_db()
    await deletable.refresh_from_db()
    assert referenced.deleted_at is not None
    assert referenced.version == 2
    assert deletable.deleted_at is not None
    assert deletable.version == 2
    assert await EndpointAuditEvent.filter(endpoint_id=referenced.id).count() == 1
    assert await JsonRpcRouteTarget.filter(endpoint_id=referenced.id).count() == 0
    event = await EndpointAuditEvent.get(endpoint_id=deletable.id)
    assert event.previous_version == 1
    assert event.new_version == 2
    assert event.changed_fields == ['deleted_at']


@pytest.mark.anyio
async def test_bulk_delete_removes_final_method_route_target(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    await _create_route(endpoint.id)
    manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    result = await manager.bulk_delete_endpoints(
        endpoint.account_id,
        endpoint.account_id,
        BulkDeleteEndpointParams(endpoint_ids=[endpoint.id]),
    )

    assert [item.id for item in result.deleted] == [endpoint.id]
    await endpoint.refresh_from_db()
    assert endpoint.deleted_at is not None
    assert endpoint.version == 2
    assert await EndpointAuditEvent.filter(endpoint_id=endpoint.id).count() == 1
    assert await JsonRpcRouteTarget.filter(endpoint_id=endpoint.id).count() == 0


@pytest.mark.anyio
async def test_bulk_delete_removes_active_http_api_reference(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001', EndpointProtocol.HTTP_API)
    app = await App.create(id='app000000000000000001', account_id=endpoint.account_id, name='Route app')
    gateway = await Gateway.create(
        id='gateway00000000000001',
        app_id=app.id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['http-api'],
    )
    route = await HttpApiRoute.create(id='route0000000000000001', gateway_id=gateway.id)
    await HttpApiRouteTarget.create(route_id=route.id, endpoint_id=endpoint.id, position=0, weight=100)
    manager = EndpointManager(DatabaseEndpointRouteReferenceLookup())

    result = await manager.bulk_delete_endpoints(
        endpoint.account_id,
        endpoint.account_id,
        BulkDeleteEndpointParams(endpoint_ids=[endpoint.id]),
    )

    assert [item.id for item in result.deleted] == [endpoint.id]
    assert await HttpApiRouteTarget.filter(endpoint_id=endpoint.id).count() == 0


@pytest.mark.anyio
async def test_bulk_delete_rejects_missing_target_before_writes(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    with pytest.raises(NotfoundError, match='Endpoint not found'):
        await manager.bulk_delete_endpoints(
            endpoint.account_id,
            endpoint.account_id,
            BulkDeleteEndpointParams(endpoint_ids=[endpoint.id, 'missing-endpoint']),
        )

    await endpoint.refresh_from_db()
    assert endpoint.deleted_at is None
    assert endpoint.version == 1
    assert await EndpointAuditEvent.filter(endpoint_id=endpoint.id).count() == 0


@pytest.mark.anyio
async def test_bulk_delete_rejects_provider_target_before_writes(route_schema: None) -> None:
    manual = await _create_endpoint('endpoint0000000000001')
    managed = await _create_endpoint('endpoint0000000000002')
    provider = await Provider.create(
        id='provider0000000000001',
        account_id=manual.account_id,
        name='Provider',
        vendor='alchemy',
        encrypted_credential='encrypted-credential',
    )
    await ProviderEndpointBinding.create(
        endpoint_id=managed.id,
        provider_id=provider.id,
        external_id='alchemy:managed',
        last_seen_at=datetime.now(UTC),
    )
    manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    with pytest.raises(BadRequestError, match='removed through their provider'):
        await manager.bulk_delete_endpoints(
            manual.account_id,
            manual.account_id,
            BulkDeleteEndpointParams(endpoint_ids=[manual.id, managed.id]),
        )

    assert await Endpoint.filter(id__in=[manual.id, managed.id], deleted_at=None, version=1).count() == 2
    assert await EndpointAuditEvent.filter(endpoint_id__in=[manual.id, managed.id]).count() == 0


@pytest.mark.anyio
async def test_manual_delete_allows_jsonrpc_reference_from_deleted_app(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    await _create_route(endpoint.id)
    await ApplicationManager.delete_app(endpoint.account_id, endpoint.account_id, 'app000000000000000001')
    manager = EndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    result = await manager.delete_endpoint(endpoint.account_id, endpoint.account_id, endpoint.id)

    assert result.deleted is True


@pytest.mark.anyio
async def test_manual_delete_allows_http_api_reference_from_deleted_app(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001', EndpointProtocol.HTTP_API)
    app = await App.create(id='app000000000000000001', account_id=endpoint.account_id, name='Route app')
    gateway = await Gateway.create(
        id='gateway00000000000001',
        app_id=app.id,
        name='ethereum-mainnet',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        transport_types=['http-api'],
    )
    route = await HttpApiRoute.create(id='route0000000000000001', gateway_id=gateway.id)
    await HttpApiRouteTarget.create(route_id=route.id, endpoint_id=endpoint.id, position=0, weight=100)
    await ApplicationManager.delete_app(endpoint.account_id, endpoint.account_id, app.id)
    manager = EndpointManager(DatabaseEndpointRouteReferenceLookup())

    result = await manager.delete_endpoint(endpoint.account_id, endpoint.account_id, endpoint.id)

    assert result.deleted is True


@pytest.mark.anyio
async def test_managed_archive_rejects_referenced_endpoint(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    await _create_route(endpoint.id)
    manager = ManagedEndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())

    async with in_transaction() as connection:
        snapshots = await manager.list_snapshots([endpoint.id], using_db=connection)
        with pytest.raises(ManagedEndpointReferencedError, match='referenced by an active RPC route'):
            await manager.archive(snapshots[endpoint.id], 'provider0000000000001', using_db=connection)

    await endpoint.refresh_from_db()
    assert endpoint.deleted_at is None


@pytest.mark.anyio
async def test_managed_reconcile_rejects_identity_drift(route_schema: None) -> None:
    endpoint = await _create_endpoint('endpoint0000000000001')
    manager = ManagedEndpointManager(DatabaseJsonRpcEndpointRouteReferenceLookup())
    params = ManagedEndpointParams(
        name=endpoint.name,
        chain=Chain.ETHEREUM,
        network=Network.SEPOLIA,
        protocol=EndpointProtocol.JSONRPC,
        url='https://rpc.example.com',
        auth=EndpointNoAuthCreateParams(),
    )

    async with in_transaction() as connection:
        snapshots = await manager.list_snapshots([endpoint.id], using_db=connection)
        with pytest.raises(ManagedEndpointValidationError, match='identity fields are immutable'):
            await manager.reconcile(snapshots[endpoint.id], 'provider0000000000001', params, using_db=connection)

    await endpoint.refresh_from_db()
    assert Network(endpoint.network) is Network.MAINNET
    assert endpoint.version == 1
