from fastlog import log
from tortoise.exceptions import IntegrityError

from app.clients.transport import HttpTransport
from app.core.errors import BadRequestError, ForbiddenError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.account import AccountStatus
from app.model.application import AppAuditAction
from app.model.endpoint import ManagedEndpointReferencedError
from app.model.provider import (
    CreateProviderParams,
    ProviderCredentialDetail,
    ProviderDeleteResult,
    ProviderDetail,
    ProviderEndpointItem,
    ProviderEndpointList,
    ProviderEndpointSyncStatus,
    ProviderItem,
    ProviderList,
    ProviderNetworkPair,
    ProviderSyncResult,
    ProviderVendor,
    UpdateProviderParams,
    validate_provider_networks,
)
from app.orm.account import Account
from app.orm.application import App
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.application import AppProviderManager
from app.services.application.audit import write_audit_event
from app.services.endpoint import ManagedEndpointStore
from app.services.provider.crypto import ProviderSecretConfigError, decrypt_provider_credential, encrypt_provider_credential
from app.services.provider.schedule import next_day_sync_at, next_provider_sync_at
from app.services.provider.sync import ProviderSyncManager
from app.util import datetime as datetime_util

MAX_PROVIDERS_PER_ACCOUNT = 15


def _dump_networks(value: list[ProviderNetworkPair]) -> list[dict[str, str]]:
    return [item.model_dump(mode='json') for item in value]


class ProviderManager:
    def __init__(self, transport: HttpTransport, endpoint_store: ManagedEndpointStore) -> None:
        self._endpoint_store = endpoint_store
        self._sync_manager = ProviderSyncManager(transport, endpoint_store)

    async def create_provider(self, account_id: str, params: CreateProviderParams) -> ProviderDetail:
        credential = params.credential.secret.get_secret_value()
        try:
            encrypted_credential = encrypt_provider_credential(credential)
        except (ValueError, ProviderSecretConfigError) as exc:
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
                    raise BadRequestError('An account can have at most 15 providers.')
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
                    only_networks=_dump_networks(params.only_networks),
                    ignore_networks=_dump_networks(params.ignore_networks),
                    version=1,
                )
        except IntegrityError as exc:
            raise BadRequestError('Provider name already exists.') from exc
        log.info(f'Provider {provider.id} created | Account:{account_id} | Vendor:{params.vendor.value}')
        return self._to_detail(provider, credential=credential)

    async def list_providers(
        self,
        account_id: str,
        *,
        vendor: list[ProviderVendor] | None = None,
        enabled: bool | None = None,
        sync_enabled: bool | None = None,
        page: int = 1,
        size: int = 20,
    ) -> ProviderList:
        query = Provider.filter(account_id=account_id, deleted_at=None)
        if vendor:
            query = query.filter(vendor__in=vendor)
        if enabled is not None:
            query = query.filter(enabled=enabled)
        if sync_enabled is not None:
            query = query.filter(sync_enabled=sync_enabled)
        total = await query.count()
        rows = await query.order_by('-created_at', '-id').offset((page - 1) * size).limit(size)
        max_page = (total + size - 1) // size if size else 0
        return ProviderList(
            page=page,
            size=size,
            total=total,
            max_page=max_page,
            items=[self._to_item(row) for row in rows],
        )

    async def get_provider(self, account_id: str, provider_id: str) -> ProviderDetail:
        provider = await self._get_provider(account_id, provider_id)
        return self._to_detail(provider)

    async def update_provider(
        self,
        account_id: str,
        provider_id: str,
        params: UpdateProviderParams,
    ) -> ProviderDetail:
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
                    return self._to_detail(provider)
                values['version'] = provider.version + 1
                values['modified_at'] = datetime_util.next_utc_timestamp(provider.modified_at)
                await Provider.filter(id=provider.id).using_db(connection).update(**values)
                provider.update_from_dict(values)
        except IntegrityError as exc:
            raise BadRequestError('Provider name already exists.') from exc
        except ProviderSecretConfigError as exc:
            raise UnavailableError('Provider credential encryption is unavailable.') from exc
        log.info(f'Provider {provider_id} updated | Account:{account_id} | Version:{provider.version}')
        return self._to_detail(provider)

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

    async def list_provider_endpoints(
        self,
        account_id: str,
        provider_id: str,
        *,
        sync_status: ProviderEndpointSyncStatus | None = None,
        page: int = 1,
        size: int = 20,
    ) -> ProviderEndpointList:
        provider = await self._get_provider(account_id, provider_id)
        query = ProviderEndpointBinding.filter(provider_id=provider.id)
        if sync_status is ProviderEndpointSyncStatus.AVAILABLE:
            query = query.filter(endpoint__deleted_at__isnull=True)
        elif sync_status is ProviderEndpointSyncStatus.MISSING:
            query = query.filter(endpoint__deleted_at__isnull=False)
        total = await query.count()
        rows = (
            await query.order_by('endpoint__chain', 'endpoint__network', 'endpoint__name').offset((page - 1) * size).limit(size)
        )
        endpoint_items = await self._endpoint_store.list_items(account_id, [row.endpoint_id for row in rows])
        max_page = (total + size - 1) // size if size else 0
        items = [
            ProviderEndpointItem(
                endpoint=endpoint_items[row.endpoint_id].endpoint,
                sync_status=(
                    ProviderEndpointSyncStatus.MISSING
                    if endpoint_items[row.endpoint_id].deleted_at is not None
                    else ProviderEndpointSyncStatus.AVAILABLE
                ),
                external_id=row.external_id,
                last_seen_at=row.last_seen_at,
                archived_at=endpoint_items[row.endpoint_id].deleted_at,
            )
            for row in rows
        ]
        return ProviderEndpointList(page=page, size=size, total=total, max_page=max_page, items=items)

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
        only_networks = params.only_networks
        ignore_networks = params.ignore_networks
        stored_only = [ProviderNetworkPair.model_validate(item) for item in provider.only_networks]
        stored_ignored = [ProviderNetworkPair.model_validate(item) for item in provider.ignore_networks]
        effective_only = only_networks if only_networks is not None else stored_only
        effective_ignored = ignore_networks if ignore_networks is not None else stored_ignored
        if effective_only and effective_ignored:
            raise BadRequestError('Provider only_networks and ignore_networks cannot both be set.')
        network_filters_changed = only_networks is not None or ignore_networks is not None
        if network_filters_changed:
            try:
                validate_provider_networks(ProviderVendor(provider.vendor), [*effective_only, *effective_ignored])
            except ValueError as exc:
                raise BadRequestError(str(exc)) from exc
        if only_networks is not None:
            values['only_networks'] = _dump_networks(only_networks)
        if ignore_networks is not None:
            values['ignore_networks'] = _dump_networks(ignore_networks)
        return values

    @staticmethod
    def _to_item(provider: Provider) -> ProviderItem:
        return ProviderItem(**provider.model_dump())

    @staticmethod
    def _to_detail(provider: Provider, *, credential: str | None = None) -> ProviderDetail:
        try:
            secret = credential if credential is not None else decrypt_provider_credential(provider.encrypted_credential)
        except ProviderSecretConfigError as exc:
            log.warning(f'Provider credential is unavailable | Account:{provider.account_id} | Provider:{provider.id}')
            raise UnavailableError('Provider credential is unavailable.') from exc
        item = ProviderManager._to_item(provider)
        values = item.model_dump(exclude={'credential'})
        credential_item = ProviderCredentialDetail(has_secret=True, secret=secret)
        return ProviderDetail(**values, credential=credential_item)
