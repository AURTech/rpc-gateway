from tortoise.backends.base.client import BaseDBAsyncClient

from app.infra.outbound_policy import HTTP_OUTBOUND_SCHEMES, OutboundTargetError, build_outbound_target_policy
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointAuditAction, EndpointProtocol, validate_endpoint_auth_url
from app.model.endpoint.managed import (
    ManagedEndpointChange,
    ManagedEndpointItem,
    ManagedEndpointParams,
    ManagedEndpointReferencedError,
    ManagedEndpointSnapshot,
    ManagedEndpointValidationError,
)
from app.orm.endpoint import Endpoint
from app.services.endpoint.auth import build_create_auth, create_auth_changed_fields
from app.services.endpoint.crypto import (
    EndpointSecretConfigError,
    decrypt_endpoint_secret,
    decrypt_endpoint_url,
    encrypt_endpoint_url,
)
from app.services.endpoint.endpoint import EndpointManager, create_endpoint_audit_event
from app.services.endpoint.interface import EndpointRouteReferenceLookup
from app.util import datetime as datetime_util


def _to_snapshot(endpoint: Endpoint) -> ManagedEndpointSnapshot:
    return ManagedEndpointSnapshot(
        id=endpoint.id,
        account_id=endpoint.account_id,
        name=endpoint.name,
        chain=Chain(endpoint.chain),
        network=Network(endpoint.network),
        protocol=EndpointProtocol(endpoint.protocol),
        enabled=endpoint.enabled,
        version=endpoint.version,
        deleted_at=endpoint.deleted_at,
        modified_at=endpoint.modified_at,
    )


class ManagedEndpointManager:
    def __init__(self, route_references: EndpointRouteReferenceLookup) -> None:
        self._route_references = route_references

    @staticmethod
    async def validate_url(url: str) -> None:
        try:
            await build_outbound_target_policy().validate_url(url, allowed_schemes=HTTP_OUTBOUND_SCHEMES)
        except OutboundTargetError as exc:
            raise ManagedEndpointValidationError('Endpoint URL is not allowed.') from exc

    @staticmethod
    async def name_exists(account_id: str, name: str, *, using_db: BaseDBAsyncClient) -> bool:
        return await Endpoint.filter(account_id=account_id, name=name).using_db(using_db).exists()

    @staticmethod
    async def list_snapshots(
        endpoint_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> dict[str, ManagedEndpointSnapshot]:
        endpoints = await Endpoint.select_for_update(using_db=using_db).filter(id__in=endpoint_ids).order_by('id')
        return {endpoint.id: _to_snapshot(endpoint) for endpoint in endpoints}

    @staticmethod
    async def create(
        account_id: str,
        actor_id: str,
        params: ManagedEndpointParams,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ManagedEndpointSnapshot:
        await ManagedEndpointManager.validate_url(params.url)
        validate_endpoint_auth_url(params.url, params.auth.type)
        auth = build_create_auth(params.auth)
        endpoint = await Endpoint.create(
            using_db=using_db,
            account_id=account_id,
            name=params.name,
            chain=params.chain,
            network=params.network,
            protocol=params.protocol,
            encrypted_url=encrypt_endpoint_url(params.url),
            enabled=params.enabled,
            version=1,
            **auth.values(),
        )
        changed_fields = [
            'name',
            'chain',
            'network',
            'protocol',
            'url',
            'enabled',
            *create_auth_changed_fields(auth),
        ]
        await create_endpoint_audit_event(
            endpoint,
            actor_id=actor_id,
            action=EndpointAuditAction.CREATED,
            previous_version=None,
            new_version=1,
            changed_fields=changed_fields,
            using_db=using_db,
        )
        return _to_snapshot(endpoint)

    @staticmethod
    async def reconcile(
        snapshot: ManagedEndpointSnapshot,
        actor_id: str,
        params: ManagedEndpointParams,
        *,
        using_db: BaseDBAsyncClient,
    ) -> tuple[ManagedEndpointSnapshot, ManagedEndpointChange]:
        await ManagedEndpointManager.validate_url(params.url)
        validate_endpoint_auth_url(params.url, params.auth.type)
        endpoint = await Endpoint.select_for_update(using_db=using_db).get(id=snapshot.id)
        values: dict[str, object] = {}
        changed_fields: list[str] = []
        identity_changed = (
            Chain(endpoint.chain) is not params.chain
            or Network(endpoint.network) is not params.network
            or EndpointProtocol(endpoint.protocol) is not params.protocol
        )
        if identity_changed:
            raise ManagedEndpointValidationError('Endpoint identity fields are immutable.')
        try:
            url_changed = decrypt_endpoint_url(endpoint.encrypted_url) != params.url
            auth_changed = not ManagedEndpointManager._auth_matches(endpoint, params)
        except EndpointSecretConfigError:
            url_changed = True
            auth_changed = True
        if url_changed:
            values['encrypted_url'] = encrypt_endpoint_url(params.url)
            changed_fields.append('url')
        if auth_changed:
            auth = build_create_auth(params.auth)
            values.update(auth.values())
            changed_fields.extend(create_auth_changed_fields(auth))
        restored = endpoint.deleted_at is not None
        if restored:
            values['deleted_at'] = None
            changed_fields.append('deleted_at')
        if not changed_fields:
            return _to_snapshot(endpoint), ManagedEndpointChange.UNCHANGED
        previous_version = endpoint.version
        version = previous_version + 1
        values['version'] = version
        values['modified_at'] = datetime_util.next_utc_timestamp(endpoint.modified_at)
        await Endpoint.filter(id=endpoint.id).using_db(using_db).update(**values)
        endpoint.update_from_dict(values)
        action = EndpointAuditAction.RESTORED if restored else EndpointAuditAction.UPDATED
        await create_endpoint_audit_event(
            endpoint,
            actor_id=actor_id,
            action=action,
            previous_version=previous_version,
            new_version=version,
            changed_fields=changed_fields,
            using_db=using_db,
        )
        change = ManagedEndpointChange.RESTORED if restored else ManagedEndpointChange.UPDATED
        return _to_snapshot(endpoint), change

    async def archive(
        self,
        snapshot: ManagedEndpointSnapshot,
        actor_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ManagedEndpointSnapshot:
        endpoint = await Endpoint.select_for_update(using_db=using_db).get(id=snapshot.id)
        if endpoint.deleted_at is not None:
            return _to_snapshot(endpoint)
        referenced_ids = await self._route_references.referenced_endpoint_ids([endpoint.id], using_db=using_db)
        if endpoint.id in referenced_ids:
            raise ManagedEndpointReferencedError('Endpoint is referenced by an active RPC route.')
        deleted_at = datetime_util.next_utc_timestamp(endpoint.modified_at)
        version = endpoint.version + 1
        values = {'deleted_at': deleted_at, 'version': version, 'modified_at': deleted_at}
        await Endpoint.filter(id=endpoint.id).using_db(using_db).update(**values)
        endpoint.update_from_dict(values)
        await create_endpoint_audit_event(
            endpoint,
            actor_id=actor_id,
            action=EndpointAuditAction.ARCHIVED,
            previous_version=snapshot.version,
            new_version=version,
            changed_fields=['deleted_at'],
            using_db=using_db,
        )
        return _to_snapshot(endpoint)

    @staticmethod
    async def detach(
        snapshot: ManagedEndpointSnapshot,
        actor_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ManagedEndpointSnapshot:
        endpoint = await Endpoint.select_for_update(using_db=using_db).get(id=snapshot.id)
        if endpoint.deleted_at is not None:
            return _to_snapshot(endpoint)
        previous_version = endpoint.version
        version = previous_version + 1
        modified_at = datetime_util.next_utc_timestamp(endpoint.modified_at)
        values = {'version': version, 'modified_at': modified_at}
        await Endpoint.filter(id=endpoint.id).using_db(using_db).update(**values)
        endpoint.update_from_dict(values)
        await create_endpoint_audit_event(
            endpoint,
            actor_id=actor_id,
            action=EndpointAuditAction.UPDATED,
            previous_version=previous_version,
            new_version=version,
            changed_fields=['provider'],
            using_db=using_db,
        )
        return _to_snapshot(endpoint)

    @staticmethod
    async def list_items(account_id: str, endpoint_ids: list[str]) -> dict[str, ManagedEndpointItem]:
        endpoints = await Endpoint.filter(id__in=endpoint_ids, account_id=account_id)
        bindings = await EndpointManager._bindings_by_endpoint(endpoint_ids)
        return {
            endpoint.id: ManagedEndpointItem(
                endpoint=EndpointManager.to_item(endpoint, binding=bindings.get(endpoint.id)),
                deleted_at=endpoint.deleted_at,
            )
            for endpoint in endpoints
        }

    @staticmethod
    def _auth_matches(endpoint: Endpoint, params: ManagedEndpointParams) -> bool:
        auth = build_create_auth(params.auth)
        if endpoint.auth_type != auth.auth_type:
            return False
        if endpoint.auth_header_name != auth.auth_header_name or endpoint.auth_query_param != auth.auth_query_param:
            return False
        if auth.encrypted_auth_secret is None:
            return endpoint.encrypted_auth_secret is None
        if endpoint.encrypted_auth_secret is None:
            return False
        expected = decrypt_endpoint_secret(auth.encrypted_auth_secret)
        return decrypt_endpoint_secret(endpoint.encrypted_auth_secret) == expected
