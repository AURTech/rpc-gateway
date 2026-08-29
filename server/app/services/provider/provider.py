from fastlog import log
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from app.clients.transport import HttpTransport
from app.core.errors import BadRequestError, ForbiddenError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.account import AccountStatus
from app.model.application import AppAuditAction
from app.model.endpoint import ManagedEndpointReferencedError
from app.model.provider import (
    CreateProviderParams,
    ProviderCredentialDetail,
    ProviderDeleteImpact,
    ProviderDeleteResult,
    ProviderEndpointCounts,
    ProviderEndpointDiscoveryStatus,
    ProviderEndpointItem,
    ProviderEndpointList,
    ProviderEndpointSyncStatus,
    ProviderItem,
    ProviderList,
    ProviderNetworkPair,
    ProviderSyncResult,
    ProviderSyncRunItem,
    ProviderSyncRunList,
    ProviderSyncRunState,
    ProviderSyncStatus,
    ProviderSyncTrigger,
    ProviderVendor,
    UpdateProviderParams,
    validate_provider_networks,
)
from app.orm.account import Account
from app.orm.application import App
from app.orm.http_api_route import HttpApiRouteTarget
from app.orm.jsonrpc_route import JsonRpcRouteTarget
from app.orm.provider import Provider, ProviderEndpointBinding, ProviderSyncRun
from app.services.application import AppProviderManager
from app.services.application.audit import write_audit_event
from app.services.endpoint import ManagedEndpointStore
from app.services.provider.crypto import ProviderCredentialConfigError, decrypt_provider_credential, encrypt_provider_credential
from app.services.provider.schedule import next_day_sync_at, next_provider_sync_at
from app.services.provider.sync import ProviderSyncManager
from app.util import datetime as datetime_util

MAX_PROVIDERS_PER_ACCOUNT = 6


def _dump_networks(value: list[ProviderNetworkPair] | None) -> list[dict[str, str]] | None:
    return [item.model_dump(mode='json') for item in value] if value is not None else None


class ProviderManager:
    def __init__(self, transport: HttpTransport, endpoint_store: ManagedEndpointStore) -> None:
        self._endpoint_store = endpoint_store
        self._sync_manager = ProviderSyncManager(transport, endpoint_store)

    async def create_provider(self, account_id: str, params: CreateProviderParams) -> ProviderItem:
        credential = params.credential.secret.get_secret_value()
        try:
            encrypted_credential = encrypt_provider_credential(credential)
        except (ValueError, ProviderCredentialConfigError) as exc:
            raise UnavailableError('Provider credential encryption is unavailable.') from exc
        next_sync_at = None
        if params.enabled and params.sync_enabled:
            next_sync_at = next_provider_sync_at(account_id, after=datetime_util.now_utc())
        try:
            async with in_tx() as connection:
                account = await Account.select_for_update(using_db=connection).get_or_none(id=account_id, deleted_at=None)
                if account is None or account.status != AccountStatus.ACTIVE:
                    raise ForbiddenError('Account is inactive.')
                provider_count = await Provider.filter(account_id=account_id, deleted_at=None).using_db(connection).count()
                if provider_count >= MAX_PROVIDERS_PER_ACCOUNT:
                    raise BadRequestError(f'An account can have at most {MAX_PROVIDERS_PER_ACCOUNT} providers.')
                provider = await Provider.create(
                    using_db=connection,
                    account_id=account_id,
                    name=params.name,
                    vendor=params.vendor,
                    enabled=params.enabled,
                    sync_enabled=params.sync_enabled,
                    next_sync_at=next_sync_at,
                    encrypted_credential=encrypted_credential,
                    settings=params.settings.model_dump(exclude_none=True),
                    networks=_dump_networks(params.networks),
                    version=1,
                )
        except IntegrityError as exc:
            raise BadRequestError('Provider name already exists.') from exc
        log.info(f'Provider {provider.id} created | Account:{account_id} | Vendor:{params.vendor.value}')
        return (await self._to_items([provider]))[0]

    async def list_providers(
        self,
        account_id: str,
        *,
        vendor: list[ProviderVendor] | None = None,
        enabled: bool | None = None,
        sync_enabled: bool | None = None,
        last_sync_status: ProviderSyncStatus | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> ProviderList:
        query = Provider.filter(account_id=account_id, deleted_at=None)
        if q:
            value = q.strip()
            query = query.filter(Q(name__icontains=value) | Q(id__icontains=value))
        if vendor:
            query = query.filter(vendor__in=vendor)
        if enabled is not None:
            query = query.filter(enabled=enabled)
        if sync_enabled is not None:
            query = query.filter(sync_enabled=sync_enabled)
        if last_sync_status is not None:
            query = query.filter(last_sync_status=last_sync_status)
        total = await query.count()
        rows = await query.order_by('-created_at', '-id').offset((page - 1) * size).limit(size)
        max_page = (total + size - 1) // size if size else 0
        items = await self._to_items(rows)
        return ProviderList(
            page=page,
            size=size,
            total=total,
            max_page=max_page,
            items=items,
        )

    async def get_provider(self, account_id: str, provider_id: str) -> ProviderItem:
        provider = await self._get_provider(account_id, provider_id)
        return (await self._to_items([provider]))[0]

    async def get_credential(self, account_id: str, provider_id: str) -> ProviderCredentialDetail:
        provider = await self._get_provider(account_id, provider_id)
        try:
            secret = decrypt_provider_credential(provider.encrypted_credential)
        except ProviderCredentialConfigError as exc:
            log.warning(f'Provider credential is unavailable | Provider:{provider.id} | Account:{account_id}')
            raise UnavailableError('Provider credential is unavailable.') from exc
        return ProviderCredentialDetail(secret=secret)

    async def update_provider(
        self,
        account_id: str,
        provider_id: str,
        params: UpdateProviderParams,
    ) -> ProviderItem:
        try:
            async with in_tx() as connection:
                provider = await Provider.select_for_update(using_db=connection).get_or_none(
                    id=provider_id,
                    account_id=account_id,
                    deleted_at=None,
                )
                if provider is None:
                    raise NotfoundError('Provider not found.')
                if provider.version != params.expected_version:
                    raise BadRequestError('Provider version conflict. Reload the provider before saving.')
                values = self._update_values(provider, params)
                if not values:
                    return (await self._to_items([provider]))[0]
                values['version'] = provider.version + 1
                values['modified_at'] = datetime_util.next_utc_timestamp(provider.modified_at)
                await Provider.filter(id=provider.id).using_db(connection).update(**values)
                provider.update_from_dict(values)
        except IntegrityError as exc:
            raise BadRequestError('Provider name already exists.') from exc
        except ProviderCredentialConfigError as exc:
            raise UnavailableError('Provider credential encryption is unavailable.') from exc
        log.info(f'Provider {provider_id} updated | Account:{account_id} | Version:{provider.version}')
        return (await self._to_items([provider]))[0]

    async def delete_provider(
        self,
        account_id: str,
        provider_id: str,
        *,
        delete_unreferenced_endpoints: bool = False,
    ) -> ProviderDeleteResult:
        """Delete one Provider without making retained Endpoints depend on its lifecycle.

        The Provider, bindings, and Endpoint rows are locked in one transaction so a concurrent sync cannot recreate or
        mutate bindings while deletion is classifying them. Endpoint connection fields remain untouched because they are
        already stored as complete encrypted configuration on each Endpoint.
        """
        archived = 0
        retained = 0
        async with in_tx() as connection:
            provider = await Provider.select_for_update(using_db=connection).get_or_none(
                id=provider_id,
                account_id=account_id,
                deleted_at=None,
            )
            if provider is None:
                raise NotfoundError('Provider not found.')
            await AppProviderManager.remove_provider_targets(
                account_id,
                provider.id,
                using_db=connection,
            )
            apps = await App.select_for_update(using_db=connection).filter(provider_id=provider.id, deleted_at=None)
            for rpc_app in apps:
                previous_version = rpc_app.version
                values = {
                    'provider_id': None,
                    'version': previous_version + 1,
                    'modified_at': datetime_util.next_utc_timestamp(rpc_app.modified_at),
                }
                await App.filter(id=rpc_app.id).using_db(connection).update(**values)
                await write_audit_event(
                    rpc_app.id,
                    account_id=account_id,
                    actor_id=account_id,
                    resource_type='app',
                    resource_id=rpc_app.id,
                    action=AppAuditAction.UPDATED,
                    previous_version=previous_version,
                    new_version=previous_version + 1,
                    changed_fields=['provider_id'],
                    using_db=connection,
                )
            bindings = await ProviderEndpointBinding.select_for_update(using_db=connection).filter(
                provider_id=provider.id,
            )
            endpoints = await self._endpoint_store.list_snapshots(
                [binding.endpoint_id for binding in bindings],
                using_db=connection,
            )
            for endpoint in endpoints.values():
                if endpoint.deleted_at is not None:
                    continue
                if delete_unreferenced_endpoints:
                    try:
                        await self._endpoint_store.archive(endpoint, account_id, using_db=connection)
                    except ManagedEndpointReferencedError:
                        await self._endpoint_store.detach(endpoint, account_id, using_db=connection)
                        retained += 1
                    else:
                        archived += 1
                else:
                    await self._endpoint_store.detach(endpoint, account_id, using_db=connection)
                    retained += 1
            await ProviderEndpointBinding.filter(provider_id=provider.id).using_db(connection).delete()
            version = provider.version + 1
            deleted_at = datetime_util.next_utc_timestamp(provider.modified_at)
            await (
                Provider.filter(id=provider.id)
                .using_db(connection)
                .update(
                    deleted_at=deleted_at,
                    modified_at=deleted_at,
                    version=version,
                )
            )
        detached = len(bindings)
        log.info(
            f'Provider {provider_id} deleted | Account:{account_id} | Archived:{archived} | '
            f'Retained:{retained} | Detached:{detached}'
        )
        return ProviderDeleteResult(
            id=provider_id,
            version=version,
            deleted=True,
            archived_endpoints=archived,
            retained_endpoints=retained,
            detached_endpoints=detached,
        )

    async def sync_provider(self, account_id: str, provider_id: str) -> ProviderSyncResult:
        result = await self._sync_manager.sync_provider(account_id, provider_id)
        next_sync_at = next_day_sync_at(account_id, after=datetime_util.now_utc())
        await Provider.filter(
            id=provider_id,
            account_id=account_id,
            deleted_at=None,
            enabled=True,
            sync_enabled=True,
        ).update(next_sync_at=next_sync_at)
        return result

    async def create_sync_run(
        self,
        account_id: str,
        provider_id: str,
        *,
        trigger: ProviderSyncTrigger,
    ) -> tuple[ProviderSyncRunItem, bool]:
        provider = await self._get_provider(account_id, provider_id)
        if not provider.enabled:
            raise BadRequestError('Provider is disabled.')
        async with in_tx() as connection:
            await Provider.select_for_update(using_db=connection).get(id=provider_id, account_id=account_id, deleted_at=None)
            active = (
                await ProviderSyncRun.filter(
                    provider_id=provider_id,
                    account_id=account_id,
                    deleted_at=None,
                    state__in=[ProviderSyncRunState.QUEUED, ProviderSyncRunState.RUNNING],
                )
                .using_db(connection)
                .order_by('-created_at')
                .first()
            )
            if active is not None:
                return self._to_run_item(active), False
            now = datetime_util.now_utc()
            run = await ProviderSyncRun.create(
                using_db=connection,
                provider_id=provider_id,
                account_id=account_id,
                trigger=trigger,
                state=ProviderSyncRunState.QUEUED,
                queued_at=now,
            )
        return self._to_run_item(run), True

    async def list_provider_endpoints(
        self,
        account_id: str,
        provider_id: str,
        *,
        include_effective_url: bool = False,
        sync_status: ProviderEndpointSyncStatus | None = None,
        discovery_status: ProviderEndpointDiscoveryStatus | None = None,
        q: str | None = None,
        chain: object | None = None,
        network: object | None = None,
        protocol: object | None = None,
        retained_by_routes: bool | None = None,
        page: int = 1,
        size: int = 20,
    ) -> ProviderEndpointList:
        provider = await self._get_provider(account_id, provider_id)
        query = ProviderEndpointBinding.filter(provider_id=provider.id)
        if discovery_status is not None:
            query = query.filter(discovery_status=discovery_status)
        if sync_status is ProviderEndpointSyncStatus.AVAILABLE:
            query = query.filter(discovery_status=ProviderEndpointDiscoveryStatus.PRESENT)
        elif sync_status is ProviderEndpointSyncStatus.MISSING:
            query = query.filter(discovery_status=ProviderEndpointDiscoveryStatus.MISSING)
        if q:
            value = q.strip()
            query = query.filter(Q(endpoint__name__icontains=value) | Q(external_id__icontains=value))
        if chain is not None:
            query = query.filter(endpoint__chain=chain)
        if network is not None:
            query = query.filter(endpoint__network=network)
        if protocol is not None:
            query = query.filter(endpoint__protocol=protocol)
        if retained_by_routes:
            query = query.filter(
                discovery_status=ProviderEndpointDiscoveryStatus.MISSING,
                endpoint__deleted_at__isnull=True,
            )
            candidate_ids = await query.values_list('endpoint_id', flat=True)
            referenced_ids = set(
                await JsonRpcRouteTarget.filter(endpoint_id__in=candidate_ids, deleted_at=None).values_list(
                    'endpoint_id', flat=True
                )
            )
            referenced_ids.update(
                await HttpApiRouteTarget.filter(endpoint_id__in=candidate_ids, deleted_at=None).values_list(
                    'endpoint_id', flat=True
                )
            )
            query = query.filter(endpoint_id__in=referenced_ids)
        total = await query.count()
        rows = (
            await query.order_by('endpoint__chain', 'endpoint__network', 'endpoint__name').offset((page - 1) * size).limit(size)
        )
        endpoint_items = await self._endpoint_store.list_items(
            account_id,
            [row.endpoint_id for row in rows],
            include_effective_url=include_effective_url,
        )
        max_page = (total + size - 1) // size if size else 0
        endpoint_ids = [row.endpoint_id for row in rows]
        referenced_ids = set(
            await JsonRpcRouteTarget.filter(endpoint_id__in=endpoint_ids, deleted_at=None).values_list('endpoint_id', flat=True)
        )
        referenced_ids.update(
            await HttpApiRouteTarget.filter(endpoint_id__in=endpoint_ids, deleted_at=None).values_list('endpoint_id', flat=True)
        )
        items = [
            ProviderEndpointItem(
                endpoint=endpoint_items[row.endpoint_id].endpoint,
                sync_status=(
                    ProviderEndpointSyncStatus.MISSING
                    if row.discovery_status == ProviderEndpointDiscoveryStatus.MISSING
                    else ProviderEndpointSyncStatus.AVAILABLE
                ),
                discovery_status=ProviderEndpointDiscoveryStatus(row.discovery_status),
                registry_state='archived' if endpoint_items[row.endpoint_id].deleted_at is not None else 'active',
                retained_by_routes=(
                    row.discovery_status == ProviderEndpointDiscoveryStatus.MISSING
                    and endpoint_items[row.endpoint_id].deleted_at is None
                    and row.endpoint_id in referenced_ids
                ),
                external_id=row.external_id,
                last_seen_at=row.last_seen_at,
                missing_since=row.missing_since,
                archived_at=endpoint_items[row.endpoint_id].deleted_at,
            )
            for row in rows
        ]
        return ProviderEndpointList(page=page, size=size, total=total, max_page=max_page, items=items)

    async def get_delete_impact(self, account_id: str, provider_id: str) -> ProviderDeleteImpact:
        provider = await self._get_provider(account_id, provider_id)
        endpoint_ids = await ProviderEndpointBinding.filter(provider_id=provider.id).values_list('endpoint_id', flat=True)
        connected_apps = await App.filter(provider_id=provider.id, deleted_at=None).count()
        json_targets = await JsonRpcRouteTarget.filter(source_provider_id=provider.id, deleted_at=None).count()
        http_targets = await HttpApiRouteTarget.filter(source_provider_id=provider.id, deleted_at=None).count()
        referenced = set(
            await JsonRpcRouteTarget.filter(endpoint_id__in=endpoint_ids, deleted_at=None).values_list('endpoint_id', flat=True)
        )
        referenced.update(
            await HttpApiRouteTarget.filter(endpoint_id__in=endpoint_ids, deleted_at=None).values_list('endpoint_id', flat=True)
        )
        managed = len(endpoint_ids)
        return ProviderDeleteImpact(
            connected_apps=connected_apps,
            automatic_route_targets=json_targets + http_targets,
            managed_endpoints=managed,
            would_detach=managed,
            would_archive=managed - len(referenced),
            would_retain=len(referenced),
        )

    async def list_sync_runs(self, account_id: str, provider_id: str, *, page: int, size: int) -> ProviderSyncRunList:
        await self._get_provider(account_id, provider_id)
        query = ProviderSyncRun.filter(provider_id=provider_id, account_id=account_id, deleted_at=None)
        total = await query.count()
        rows = await query.order_by('-created_at', '-id').offset((page - 1) * size).limit(size)
        return ProviderSyncRunList(
            page=page,
            size=size,
            total=total,
            max_page=(total + size - 1) // size,
            items=[self._to_run_item(row) for row in rows],
        )

    async def get_sync_run(self, account_id: str, provider_id: str, run_id: str) -> ProviderSyncRunItem:
        await self._get_provider(account_id, provider_id)
        run = await ProviderSyncRun.filter(id=run_id, provider_id=provider_id, account_id=account_id, deleted_at=None).first()
        if run is None:
            raise NotfoundError('Provider sync run not found.')
        return self._to_run_item(run)

    @staticmethod
    async def _get_provider(account_id: str, provider_id: str) -> Provider:
        provider = await Provider.filter(id=provider_id, account_id=account_id, deleted_at=None).first()
        if provider is None:
            raise NotfoundError('Provider not found.')
        return provider

    @staticmethod
    def _update_values(provider: Provider, params: UpdateProviderParams) -> dict[str, object]:
        values: dict[str, object] = {}
        fields = params.model_fields_set
        for name in ('name', 'enabled', 'sync_enabled'):
            if name not in fields:
                continue
            value = params.model_dump()[name]
            if value != provider.model_dump().get(name):
                values[name] = value
        if 'enabled' in values or 'sync_enabled' in values:
            enabled = values.get('enabled', provider.enabled)
            sync_enabled = values.get('sync_enabled', provider.sync_enabled)
            values['next_sync_at'] = (
                next_provider_sync_at(provider.account_id, after=datetime_util.now_utc()) if enabled and sync_enabled else None
            )
        if params.credential is not None:
            values['encrypted_credential'] = encrypt_provider_credential(params.credential.secret.get_secret_value())
        if params.settings is not None:
            values['settings'] = params.settings.model_dump(exclude_none=True)
        if 'networks' in fields:
            try:
                validate_provider_networks(ProviderVendor(provider.vendor), params.networks or [])
            except ValueError as exc:
                raise BadRequestError(str(exc)) from exc
            values['networks'] = _dump_networks(params.networks)
        return values

    @staticmethod
    def _to_run_item(run: ProviderSyncRun) -> ProviderSyncRunItem:
        endpoint_changes = run.created + run.updated + run.restored + run.archived
        return ProviderSyncRunItem(
            id=run.id,
            trigger=run.trigger,
            state=run.state,
            queued_at=run.queued_at,
            started_at=run.started_at,
            endpoint_changes=endpoint_changes,
            error=run.error,
        )

    @staticmethod
    async def _to_items(providers: list[Provider]) -> list[ProviderItem]:
        provider_ids = [provider.id for provider in providers]
        bindings = await ProviderEndpointBinding.filter(provider_id__in=provider_ids)
        app_rows = await App.filter(provider_id__in=provider_ids, deleted_at=None).values_list('provider_id')
        apps = [row[0] for row in app_rows]
        syncing_provider_ids = set(
            await ProviderSyncRun.filter(
                provider_id__in=provider_ids,
                deleted_at=None,
                state__in=[ProviderSyncRunState.QUEUED, ProviderSyncRunState.RUNNING],
            ).values_list('provider_id', flat=True)
        )
        counts = {provider_id: ProviderEndpointCounts() for provider_id in provider_ids}
        for binding in bindings:
            count = counts[binding.provider_id]
            if binding.discovery_status == ProviderEndpointDiscoveryStatus.PRESENT:
                count.present += 1
            else:
                count.missing += 1
        app_counts = {provider_id: apps.count(provider_id) for provider_id in provider_ids}
        return [
            ProviderItem(
                **provider.model_dump(),
                endpoint_counts=counts[provider.id],
                connected_app_count=app_counts[provider.id],
                syncing=provider.id in syncing_provider_ids,
            )
            for provider in providers
        ]
