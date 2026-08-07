from fastlog import log
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError, NoValuesFetched

from app.core.auth_context import get_pat_id
from app.core.errors import BadRequestError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.infra.outbound_policy import HTTP_OUTBOUND_SCHEMES, OutboundTargetError, build_outbound_target_policy
from app.model.blockchain import Chain, Network, validate_chain_network
from app.model.endpoint import (
    BulkDeleteEndpointParams,
    BulkDeleteEndpointResult,
    CreateEndpointParams,
    EndpointAuditAction,
    EndpointAuditEventItem,
    EndpointAuditEventList,
    EndpointAuthDetail,
    EndpointAuthType,
    EndpointBearerAuthDetail,
    EndpointDeleteResult,
    EndpointDetail,
    EndpointHeaderAuthDetail,
    EndpointItem,
    EndpointList,
    EndpointNoAuthPublic,
    EndpointOriginType,
    EndpointPathAuthDetail,
    EndpointProtocol,
    EndpointProviderSummary,
    EndpointQueryAuthDetail,
    EndpointTrustLevel,
    UpdateEndpointParams,
    validate_endpoint_auth_url,
    validate_endpoint_url,
)
from app.model.provider import ProviderVendor
from app.orm.endpoint import Endpoint, EndpointAuditEvent
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.endpoint.auth import auth_update_values, build_create_auth, create_auth_changed_fields
from app.services.endpoint.crypto import (
    EndpointSecretConfigError,
    decrypt_endpoint_secret,
    decrypt_endpoint_url,
    encrypt_endpoint_url,
)
from app.services.endpoint.interface import EndpointRouteReferenceLookup
from app.services.endpoint.transport import build_endpoint_url
from app.util import datetime as datetime_util

_CREATE_BASE_CHANGED_FIELDS = [
    'name',
    'chain',
    'network',
    'protocol',
    'url',
    'enabled',
    'trust_level',
]


async def create_endpoint_audit_event(
    endpoint: Endpoint,
    *,
    actor_id: str,
    action: EndpointAuditAction,
    previous_version: int | None,
    new_version: int,
    changed_fields: list[str],
    using_db: BaseDBAsyncClient,
) -> None:
    await EndpointAuditEvent.create(
        using_db=using_db,
        endpoint_id=endpoint.id,
        account_id=endpoint.account_id,
        actor_id=actor_id,
        actor_token_id=get_pat_id(),
        action=action,
        previous_version=previous_version,
        new_version=new_version,
        changed_fields=changed_fields,
    )


class EndpointManager:
    def __init__(self, route_references: EndpointRouteReferenceLookup) -> None:
        self._route_references = route_references

    async def create_endpoint(self, account_id: str, actor_id: str, params: CreateEndpointParams) -> EndpointDetail:
        """Create one manual endpoint and its audit event in one transaction.

        Raises:
            BadRequestError: the endpoint name or auth configuration is invalid.
            UnavailableError: endpoint encryption is unavailable.
        """
        try:
            validate_chain_network(params.chain, params.network)
            await build_outbound_target_policy().validate_url(params.url, allowed_schemes=HTTP_OUTBOUND_SCHEMES)
            encrypted_url = encrypt_endpoint_url(params.url)
            auth_columns = build_create_auth(params.auth)
        except (OutboundTargetError, ValueError) as exc:
            raise BadRequestError(str(exc)) from exc
        except EndpointSecretConfigError as exc:
            log.warning(f'Endpoint encryption is unavailable | Account:{account_id}')
            raise UnavailableError('Endpoint encryption is unavailable.') from exc

        try:
            async with in_tx() as connection:
                endpoint = await Endpoint.create(
                    using_db=connection,
                    account_id=account_id,
                    name=params.name,
                    chain=params.chain,
                    network=params.network,
                    protocol=params.protocol,
                    encrypted_url=encrypted_url,
                    enabled=params.enabled,
                    trust_level=params.trust_level,
                    version=1,
                    **auth_columns.values(),
                )
                changed_fields = [*_CREATE_BASE_CHANGED_FIELDS, *create_auth_changed_fields(auth_columns)]
                await create_endpoint_audit_event(
                    endpoint,
                    actor_id=actor_id,
                    action=EndpointAuditAction.CREATED,
                    previous_version=None,
                    new_version=1,
                    changed_fields=changed_fields,
                    using_db=connection,
                )
        except IntegrityError as exc:
            log.warning(f'Endpoint name already exists | Account:{account_id}')
            raise BadRequestError('Endpoint name already exists.') from exc
        log.info(f'Endpoint {endpoint.id} created | Account:{account_id} | Actor:{actor_id}')
        return EndpointManager.to_detail(endpoint)

    async def list_endpoints(
        self,
        account_id: str,
        *,
        chain: list[Chain] | None = None,
        network: list[Network] | None = None,
        protocol: EndpointProtocol | None = None,
        enabled: bool | None = None,
        origin_type: EndpointOriginType | None = None,
        provider_id: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> EndpointList:
        query = Endpoint.filter(account_id=account_id, deleted_at=None)
        if chain:
            query = query.filter(chain__in=chain)
        if network:
            query = query.filter(network__in=network)
        if protocol is not None:
            query = query.filter(protocol=protocol)
        if enabled is not None:
            query = query.filter(enabled=enabled)
        if origin_type is not None:
            query = query.filter(provider_binding__provider_id__isnull=origin_type is EndpointOriginType.MANUAL)
        if provider_id is not None:
            query = query.filter(provider_binding__provider_id=provider_id)
        total = await query.count()
        rows = await query.order_by('-created_at', '-id').offset((page - 1) * size).limit(size)
        bindings = await EndpointManager._bindings_by_endpoint([row.id for row in rows])
        max_page = (total + size - 1) // size if size else 0
        return EndpointList(
            page=page,
            size=size,
            total=total,
            max_page=max_page,
            items=[EndpointManager.to_item(row, binding=bindings.get(row.id)) for row in rows],
        )

    async def get_endpoint(self, account_id: str, endpoint_id: str) -> EndpointDetail:
        endpoint = await EndpointManager._get_owned_endpoint(account_id, endpoint_id)
        binding = await EndpointManager._binding(endpoint.id)
        return EndpointManager.to_detail(endpoint, binding=binding)

    async def update_endpoint(
        self,
        account_id: str,
        actor_id: str,
        endpoint_id: str,
        params: UpdateEndpointParams,
    ) -> EndpointDetail:
        """Update one endpoint with optimistic version checking and transactional audit.

        Raises:
            BadRequestError: the expected version is stale or updated configuration is invalid.
            NotfoundError: the endpoint does not exist or is not owned by the account.
            UnavailableError: encrypted endpoint configuration cannot be read or replaced.
        """
        if params.url is not None:
            try:
                await build_outbound_target_policy().validate_url(params.url, allowed_schemes=HTTP_OUTBOUND_SCHEMES)
            except OutboundTargetError as exc:
                raise BadRequestError(str(exc)) from exc
        try:
            async with in_tx() as connection:
                endpoint = await Endpoint.select_for_update(using_db=connection).get_or_none(
                    id=endpoint_id,
                    account_id=account_id,
                    deleted_at=None,
                )
                if endpoint is None:
                    raise NotfoundError('Endpoint not found.')
                if endpoint.version != params.expected_version:
                    raise BadRequestError('Endpoint version conflict. Reload the endpoint before saving.')
                binding = await EndpointManager._binding(endpoint.id, using_db=connection)
                if binding is not None:
                    managed_fields = params.model_fields_set - {'expected_version', 'name', 'enabled', 'trust_level'}
                    if managed_fields:
                        raise BadRequestError('Provider-managed endpoint connection fields are read-only.')
                values, changed_fields = EndpointManager._update_values(endpoint, params)
                if not changed_fields:
                    return EndpointManager.to_detail(endpoint, binding=binding)
                previous_version = endpoint.version
                new_version = previous_version + 1
                values['version'] = new_version
                values['modified_at'] = datetime_util.next_utc_timestamp(endpoint.modified_at)
                await Endpoint.filter(id=endpoint.id).using_db(connection).update(**values)
                endpoint.update_from_dict(values)
                await create_endpoint_audit_event(
                    endpoint,
                    actor_id=actor_id,
                    action=EndpointAuditAction.UPDATED,
                    previous_version=previous_version,
                    new_version=new_version,
                    changed_fields=changed_fields,
                    using_db=connection,
                )
        except IntegrityError as exc:
            log.warning(f'Endpoint name already exists | Account:{account_id} | Endpoint:{endpoint_id}')
            raise BadRequestError('Endpoint name already exists.') from exc
        except EndpointSecretConfigError as exc:
            log.warning(f'Endpoint secret is unavailable | Account:{account_id} | Endpoint:{endpoint_id}')
            raise UnavailableError('Endpoint encrypted configuration is unavailable.') from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        log.info(f'Endpoint {endpoint_id} updated | Account:{account_id} | Actor:{actor_id} | Version:{new_version}')
        return EndpointManager.to_detail(endpoint, binding=binding)

    async def delete_endpoint(self, account_id: str, actor_id: str, endpoint_id: str) -> EndpointDeleteResult:
        """Soft-delete an owned endpoint and write the audit event atomically."""
        async with in_tx() as connection:
            endpoint = await Endpoint.select_for_update(using_db=connection).get_or_none(
                id=endpoint_id,
                account_id=account_id,
                deleted_at=None,
            )
            if endpoint is None:
                raise NotfoundError('Endpoint not found.')
            referenced_ids = await self._route_references.referenced_endpoint_ids([endpoint.id], using_db=connection)
            if endpoint.id in referenced_ids:
                raise BadRequestError('Endpoint is referenced by an active RPC route.')
            if await ProviderEndpointBinding.filter(endpoint_id=endpoint.id).using_db(connection).exists():
                raise BadRequestError('Provider-managed endpoints must be removed through their provider.')
            previous_version = endpoint.version
            new_version = previous_version + 1
            deleted_at = datetime_util.next_utc_timestamp(endpoint.modified_at)
            values = {'deleted_at': deleted_at, 'modified_at': deleted_at, 'version': new_version}
            await Endpoint.filter(id=endpoint.id).using_db(connection).update(**values)
            endpoint.update_from_dict(values)
            await create_endpoint_audit_event(
                endpoint,
                actor_id=actor_id,
                action=EndpointAuditAction.DELETED,
                previous_version=previous_version,
                new_version=new_version,
                changed_fields=['deleted_at'],
                using_db=connection,
            )
        log.info(f'Endpoint {endpoint_id} deleted | Account:{account_id} | Actor:{actor_id}')
        return EndpointDeleteResult(id=endpoint.id, version=new_version, deleted=True)

    async def bulk_delete_endpoints(
        self,
        account_id: str,
        actor_id: str,
        params: BulkDeleteEndpointParams,
    ) -> BulkDeleteEndpointResult:
        """Soft-delete every unreferenced manual Endpoint in one transaction.

        Missing, foreign, or Provider-managed targets reject the whole request. Endpoints
        referenced by active routes remain unchanged and are returned to the caller.
        """
        endpoint_ids = params.endpoint_ids
        sorted_ids = sorted(endpoint_ids)
        async with in_tx() as connection:
            endpoints = await (
                Endpoint.select_for_update(using_db=connection)
                .filter(id__in=sorted_ids, account_id=account_id, deleted_at=None)
                .order_by('id')
            )
            endpoints_by_id = {endpoint.id: endpoint for endpoint in endpoints}
            if len(endpoints_by_id) != len(endpoint_ids):
                raise NotfoundError('Endpoint not found.')
            if await ProviderEndpointBinding.filter(endpoint_id__in=sorted_ids).using_db(connection).exists():
                raise BadRequestError('Provider-managed endpoints must be removed through their provider.')

            referenced_ids = await self._route_references.referenced_endpoint_ids(sorted_ids, using_db=connection)
            deleted_endpoints: list[Endpoint] = []
            previous_versions: dict[str, int] = {}
            for endpoint in endpoints:
                if endpoint.id in referenced_ids:
                    continue
                previous_versions[endpoint.id] = endpoint.version
                endpoint.version += 1
                deleted_at = datetime_util.next_utc_timestamp(endpoint.modified_at)
                endpoint.deleted_at = deleted_at
                endpoint.modified_at = deleted_at
                deleted_endpoints.append(endpoint)

            if deleted_endpoints:
                await Endpoint.bulk_update(
                    deleted_endpoints,
                    fields=['deleted_at', 'modified_at', 'version'],
                    using_db=connection,
                )
                for endpoint in deleted_endpoints:
                    await create_endpoint_audit_event(
                        endpoint,
                        actor_id=actor_id,
                        action=EndpointAuditAction.DELETED,
                        previous_version=previous_versions[endpoint.id],
                        new_version=endpoint.version,
                        changed_fields=['deleted_at'],
                        using_db=connection,
                    )

        deleted_ids = {endpoint.id for endpoint in deleted_endpoints}
        deleted = [
            EndpointDeleteResult(id=endpoint_id, version=endpoints_by_id[endpoint_id].version, deleted=True)
            for endpoint_id in endpoint_ids
            if endpoint_id in deleted_ids
        ]
        ordered_referenced_ids = [endpoint_id for endpoint_id in endpoint_ids if endpoint_id in referenced_ids]
        log.info(
            f'Endpoints deleted | Account:{account_id} | Actor:{actor_id} | '
            f'Deleted:{len(deleted)} | Referenced:{len(ordered_referenced_ids)}'
        )
        return BulkDeleteEndpointResult(
            total=len(endpoint_ids),
            deleted=deleted,
            referenced_ids=ordered_referenced_ids,
        )

    async def list_audit_events(
        self,
        account_id: str,
        endpoint_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> EndpointAuditEventList:
        await EndpointManager._get_owned_endpoint(account_id, endpoint_id)
        query = EndpointAuditEvent.filter(endpoint_id=endpoint_id, account_id=account_id)
        total = await query.count()
        rows = await query.order_by('-created_at', '-id').offset((page - 1) * size).limit(size)
        max_page = (total + size - 1) // size if size else 0
        return EndpointAuditEventList(
            page=page,
            size=size,
            total=total,
            max_page=max_page,
            items=[EndpointAuditEventItem(**row.model_dump()) for row in rows],
        )

    @staticmethod
    def _update_values(endpoint: Endpoint, params: UpdateEndpointParams) -> tuple[dict[str, object], list[str]]:
        values: dict[str, object] = {}
        changed_fields: list[str] = []
        fields_set = params.model_fields_set

        if 'name' in fields_set and params.name != endpoint.name:
            values['name'] = params.name
            changed_fields.append('name')
        if 'enabled' in fields_set and params.enabled != endpoint.enabled:
            values['enabled'] = params.enabled
            changed_fields.append('enabled')
        stored_trust = EndpointTrustLevel(endpoint.trust_level)
        if 'trust_level' in fields_set and params.trust_level is not stored_trust:
            values['trust_level'] = params.trust_level
            changed_fields.append('trust_level')

        stored_protocol = EndpointProtocol(endpoint.protocol)
        if 'url' in fields_set and params.url is not None:
            normalized_url = validate_endpoint_url(params.url, stored_protocol)
            stored_url = decrypt_endpoint_url(endpoint.encrypted_url)
            if normalized_url != stored_url:
                values['encrypted_url'] = encrypt_endpoint_url(normalized_url)
                changed_fields.append('url')

        if 'auth' in fields_set and params.auth is not None:
            auth_values, auth_changed_fields = auth_update_values(endpoint, params.auth)
            values.update(auth_values)
            changed_fields.extend(auth_changed_fields)
        effective_url = params.url if params.url is not None else decrypt_endpoint_url(endpoint.encrypted_url)
        effective_auth_type = params.auth.type if params.auth is not None else EndpointAuthType(endpoint.auth_type)
        validate_endpoint_auth_url(effective_url, effective_auth_type)
        return values, changed_fields

    @staticmethod
    async def _get_owned_endpoint(account_id: str, endpoint_id: str) -> Endpoint:
        endpoint = await Endpoint.filter(id=endpoint_id, account_id=account_id, deleted_at=None).first()
        if endpoint is None:
            raise NotfoundError('Endpoint not found.')
        return endpoint

    @staticmethod
    async def _binding(
        endpoint_id: str,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> ProviderEndpointBinding | None:
        query = ProviderEndpointBinding.filter(endpoint_id=endpoint_id).select_related('provider')
        if using_db is not None:
            query = query.using_db(using_db)
        return await query.first()

    @staticmethod
    async def _bindings_by_endpoint(endpoint_ids: list[str]) -> dict[str, ProviderEndpointBinding]:
        if not endpoint_ids:
            return {}
        rows = await ProviderEndpointBinding.filter(endpoint_id__in=endpoint_ids).select_related('provider')
        return {row.endpoint_id: row for row in rows}

    @staticmethod
    def to_item(endpoint: Endpoint, *, binding: ProviderEndpointBinding | None = None) -> EndpointItem:
        try:
            provider_summary: EndpointProviderSummary | None = None
            if binding is not None:
                try:
                    provider = binding.provider
                except (AttributeError, NoValuesFetched) as exc:
                    raise ValueError('Provider binding relation was not loaded.') from exc
                if not isinstance(provider, Provider):
                    raise ValueError('Provider binding relation is invalid.')
                vendor = ProviderVendor(provider.vendor)
                provider_summary = EndpointProviderSummary(
                    id=provider.id,
                    name=provider.name,
                    vendor=vendor,
                    vendor_label=vendor.label,
                )
            return EndpointItem(
                url=build_endpoint_url(endpoint),
                **endpoint.model_dump(
                    provider=provider_summary.model_dump() if provider_summary else None,
                    provider_external_id=binding.external_id if binding is not None else None,
                    provider_last_seen_at=binding.last_seen_at if binding is not None else None,
                ),
            )
        except (EndpointSecretConfigError, ValueError) as exc:
            log.warning(f'Endpoint configuration is unavailable | Endpoint:{endpoint.id}')
            raise UnavailableError('Endpoint configuration is unavailable.') from exc

    @staticmethod
    def to_detail(endpoint: Endpoint, *, binding: ProviderEndpointBinding | None = None) -> EndpointDetail:
        item = EndpointManager.to_item(endpoint, binding=binding)
        try:
            configured_url = decrypt_endpoint_url(endpoint.encrypted_url)
            auth = EndpointManager._to_auth_detail(endpoint)
            values = item.model_dump(exclude={'auth'})
            return EndpointDetail(**values, configured_url=configured_url, auth=auth)
        except (EndpointSecretConfigError, ValueError) as exc:
            log.warning(f'Endpoint configuration is unavailable | Endpoint:{endpoint.id}')
            raise UnavailableError('Endpoint configuration is unavailable.') from exc

    @staticmethod
    def _to_auth_detail(endpoint: Endpoint) -> EndpointAuthDetail:
        auth_type = EndpointAuthType(endpoint.auth_type)
        if auth_type is EndpointAuthType.NONE:
            return EndpointNoAuthPublic()
        if endpoint.encrypted_auth_secret is None:
            raise ValueError('Endpoint encrypted auth secret is unavailable.')
        secret = decrypt_endpoint_secret(endpoint.encrypted_auth_secret)
        if auth_type is EndpointAuthType.BEARER:
            return EndpointBearerAuthDetail(secret=secret)
        if auth_type is EndpointAuthType.HEADER_API_KEY:
            if endpoint.auth_header_name is None:
                raise ValueError('Endpoint auth header name is unavailable.')
            return EndpointHeaderAuthDetail(header_name=endpoint.auth_header_name, secret=secret)
        if auth_type is EndpointAuthType.QUERY_API_KEY:
            if endpoint.auth_query_param is None:
                raise ValueError('Endpoint auth query parameter is unavailable.')
            return EndpointQueryAuthDetail(query_param=endpoint.auth_query_param, secret=secret)
        return EndpointPathAuthDetail(secret=secret)
