from dataclasses import dataclass, field
from hashlib import sha256

from fastlog import log
from pydantic import SecretStr
from tortoise.backends.base.client import BaseDBAsyncClient

from app.clients.provider import (
    DiscoveredEndpoint,
    ProviderDiscoveryConfig,
    ProviderDiscoveryError,
    ProviderDiscoveryFailure,
    build_provider_adapter,
)
from app.clients.transport import HttpTransport
from app.core.errors import BadRequestError, ForbiddenError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.account import AccountStatus
from app.model.blockchain import Chain, Network
from app.model.endpoint import (
    EndpointAuthType,
    EndpointBearerAuthCreateParams,
    EndpointCreateAuthParams,
    EndpointHeaderAuthCreateParams,
    EndpointNoAuthCreateParams,
    EndpointPathAuthCreateParams,
    EndpointProtocol,
    EndpointQueryAuthCreateParams,
    ManagedEndpointChange,
    ManagedEndpointParams,
    ManagedEndpointReferencedError,
    ManagedEndpointSnapshot,
    ManagedEndpointValidationError,
)
from app.model.provider import (
    ProviderEndpointAction,
    ProviderEndpointDiscoveryStatus,
    ProviderNetworkPair,
    ProviderSettingsParams,
    ProviderSyncItem,
    ProviderSyncResult,
    ProviderSyncStatus,
    ProviderVendor,
)
from app.model.provider.capability import provider_transports
from app.model.transport import Transport
from app.orm.account import Account
from app.orm.provider import Provider, ProviderEndpointBinding
from app.services.application import AppProviderManager
from app.services.endpoint import ManagedEndpointStore
from app.services.provider.crypto import ProviderCredentialConfigError, decrypt_provider_credential
from app.util import datetime as datetime_util

PROVIDER_NAME_LENGTH = 24


@dataclass(slots=True)
class _SyncCounters:
    created: int = 0
    updated: int = 0
    restored: int = 0
    archived: int = 0
    skipped: int = 0
    route_targets_added: int = 0
    route_targets_removed: int = 0
    route_targets_skipped: int = 0
    items: list[ProviderSyncItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ManagedEndpoint:
    binding: ProviderEndpointBinding
    endpoint: ManagedEndpointSnapshot


def _network_filter(value: object) -> set[tuple[Chain, Network]]:
    if not isinstance(value, list):
        return set()
    pairs: set[tuple[Chain, Network]] = set()
    for item in value:
        try:
            pair = ProviderNetworkPair.model_validate(item)
        except ValueError:
            continue
        pairs.add((pair.chain, pair.network))
    return pairs


def _create_auth(discovered: DiscoveredEndpoint) -> EndpointCreateAuthParams:
    secret = discovered.auth_secret or ''
    match discovered.auth_type:
        case EndpointAuthType.NONE:
            params = EndpointNoAuthCreateParams()
        case EndpointAuthType.BEARER:
            params = EndpointBearerAuthCreateParams(secret=SecretStr(secret))
        case EndpointAuthType.HEADER_API_KEY:
            params = EndpointHeaderAuthCreateParams(header_name=discovered.auth_name or '', secret=SecretStr(secret))
        case EndpointAuthType.QUERY_API_KEY:
            params = EndpointQueryAuthCreateParams(query_param=discovered.auth_name or '', secret=SecretStr(secret))
        case EndpointAuthType.PATH_API_KEY:
            params = EndpointPathAuthCreateParams(secret=SecretStr(secret))
        case _:
            raise ValueError('Provider endpoint auth type is unsupported.')
    return params


def _managed_params(name: str, discovered: DiscoveredEndpoint) -> ManagedEndpointParams:
    return ManagedEndpointParams(
        name=name,
        chain=discovered.chain,
        network=discovered.network,
        protocol=discovered.protocol,
        url=discovered.url,
        auth=_create_auth(discovered),
    )


class ProviderSyncManager:
    def __init__(self, transport: HttpTransport, endpoint_store: ManagedEndpointStore) -> None:
        self._transport = transport
        self._endpoint_store = endpoint_store

    async def sync_provider(self, account_id: str, provider_id: str) -> ProviderSyncResult:
        """Discover and atomically publish one Provider inventory without destructive partial updates."""
        provider = await self._get_provider(account_id, provider_id)
        if not provider.enabled:
            raise BadRequestError('Provider is disabled.')
        try:
            credential = decrypt_provider_credential(provider.encrypted_credential)
            settings = ProviderSettingsParams.model_validate(provider.settings)
        except (ProviderCredentialConfigError, ValueError) as exc:
            raise UnavailableError('Provider configuration is unavailable.') from exc
        adapter = build_provider_adapter(ProviderVendor(provider.vendor), self._transport)
        config = ProviderDiscoveryConfig(credential=credential, settings=settings)
        try:
            discovery = await adapter.discover(config, lambda: self._check_account(account_id))
        except ForbiddenError:
            raise
        except ProviderDiscoveryError as exc:
            return await self._record_failed(provider, error=str(exc))
        except Exception:
            return await self._record_failed(provider, error='Provider discovery failed.')

        filtered = self._filter_discovery(provider, discovery.items)
        allowed: list[DiscoveredEndpoint] = []
        failures = list(discovery.failures)
        for item in filtered:
            try:
                await self._endpoint_store.validate_url(item.url)
            except ManagedEndpointValidationError:
                failures.append(
                    ProviderDiscoveryFailure(
                        external_id=item.external_id,
                        error='Provider endpoint URL is not allowed.',
                    )
                )
            else:
                allowed.append(item)

        counters = _SyncCounters(skipped=len(failures))
        counters.items.extend(
            ProviderSyncItem(
                action=ProviderEndpointAction.FAILED,
                external_id=failure.external_id,
                error=failure.error,
            )
            for failure in failures
        )
        async with in_tx() as connection:
            await self._lock_account(account_id, using_db=connection)
            provider = await self._lock_provider(
                account_id,
                provider_id,
                expected_version=provider.version,
                using_db=connection,
            )
            managed_endpoints = await self._provider_endpoints_with_archived(provider.id, using_db=connection)
            endpoint_by_external_id = {row.binding.external_id: row for row in managed_endpoints}
            seen_external_ids: set[str] = set()
            protected_external_ids = {failure.external_id for failure in failures if failure.external_id}
            for item in allowed:
                seen_external_ids.add(item.external_id)
                managed = endpoint_by_external_id.get(item.external_id)
                legacy_migrated = False
                if managed is None:
                    legacy = next(
                        (
                            endpoint_by_external_id[alias]
                            for alias in item.legacy_external_ids
                            if alias in endpoint_by_external_id
                            and endpoint_by_external_id[alias].endpoint.chain is item.chain
                            and endpoint_by_external_id[alias].endpoint.network is item.network
                            and endpoint_by_external_id[alias].endpoint.protocol is item.protocol
                        ),
                        None,
                    )
                    if legacy is not None:
                        previous_external_id = legacy.binding.external_id
                        await (
                            ProviderEndpointBinding.filter(endpoint_id=legacy.endpoint.id)
                            .using_db(connection)
                            .update(external_id=item.external_id)
                        )
                        legacy.binding.external_id = item.external_id
                        endpoint_by_external_id.pop(previous_external_id)
                        endpoint_by_external_id[item.external_id] = legacy
                        managed = legacy
                        legacy_migrated = True
                if managed is None:
                    managed = await self._create_endpoint(provider, item, using_db=connection)
                    endpoint_by_external_id[item.external_id] = managed
                    counters.created += 1
                    action = ProviderEndpointAction.CREATED
                else:
                    identity_changed = (
                        managed.endpoint.chain is not item.chain
                        or managed.endpoint.network is not item.network
                        or managed.endpoint.protocol is not item.protocol
                    )
                    if identity_changed:
                        now = datetime_util.now_utc()
                        await (
                            ProviderEndpointBinding.filter(endpoint_id=managed.endpoint.id)
                            .using_db(connection)
                            .update(
                                last_seen_at=now,
                                discovery_status=ProviderEndpointDiscoveryStatus.PRESENT,
                                missing_since=None,
                            )
                        )
                        counters.skipped += 1
                        counters.items.append(
                            ProviderSyncItem(
                                chain=item.chain,
                                network=item.network,
                                action=ProviderEndpointAction.FAILED,
                                endpoint_id=managed.endpoint.id,
                                external_id=item.external_id,
                                error='Provider endpoint identity changed for an existing external ID.',
                            )
                        )
                        continue
                    action = await self._update_endpoint(provider, managed, item, using_db=connection)
                    if action is None and legacy_migrated:
                        action = ProviderEndpointAction.UPDATED
                    if action is ProviderEndpointAction.RESTORED:
                        counters.restored += 1
                    elif action is ProviderEndpointAction.UPDATED:
                        counters.updated += 1
                    else:
                        continue
                counters.items.append(
                    ProviderSyncItem(
                        chain=item.chain,
                        network=item.network,
                        action=action,
                        endpoint_id=managed.endpoint.id,
                        external_id=item.external_id,
                    )
                )
            if discovery.complete:
                missing_endpoint_ids = [
                    row.endpoint.id
                    for row in managed_endpoints
                    if row.endpoint.deleted_at is None
                    and row.binding.external_id not in seen_external_ids
                    and row.binding.external_id not in protected_external_ids
                ]
                removed = await AppProviderManager.remove_provider_targets(
                    account_id,
                    provider.id,
                    endpoint_ids=missing_endpoint_ids,
                    using_db=connection,
                )
                counters.route_targets_removed += removed.removed
                counters.archived = await self._archive_missing(
                    provider,
                    managed_endpoints,
                    seen_external_ids,
                    protected_external_ids,
                    counters=counters,
                    using_db=connection,
                )
            bound = await AppProviderManager.bind_provider_endpoints(
                account_id,
                provider.id,
                using_db=connection,
            )
            counters.route_targets_added += bound.added
            counters.route_targets_skipped += bound.skipped
            counters.skipped += bound.skipped
            status = ProviderSyncStatus.SUCCESS
            if counters.skipped or not discovery.complete:
                status = ProviderSyncStatus.PARTIAL
            await self._update_sync_state(provider, status=status, using_db=connection)
        log.info(
            f'Provider synced | Account:{account_id} | Provider:{provider.id} | Status:{status.value} | '
            f'Created:{counters.created} | Updated:{counters.updated} | Restored:{counters.restored} | '
            f'Archived:{counters.archived} | Skipped:{counters.skipped}'
        )
        return ProviderSyncResult(
            provider_id=provider.id,
            status=status,
            created=counters.created,
            updated=counters.updated,
            restored=counters.restored,
            archived=counters.archived,
            skipped=counters.skipped,
            route_targets_added=counters.route_targets_added,
            route_targets_removed=counters.route_targets_removed,
            route_targets_skipped=counters.route_targets_skipped,
            items=counters.items,
        )

    @staticmethod
    async def _get_provider(account_id: str, provider_id: str) -> Provider:
        provider = await Provider.filter(id=provider_id, account_id=account_id, deleted_at=None).first()
        if provider is None:
            raise NotfoundError('Provider not found.')
        return provider

    @staticmethod
    async def _check_account(account_id: str) -> None:
        active = await Account.filter(id=account_id, deleted_at=None, status=AccountStatus.ACTIVE).exists()
        if not active:
            raise ForbiddenError('Account is inactive.')

    @staticmethod
    async def _lock_account(account_id: str, *, using_db: BaseDBAsyncClient) -> None:
        account = await Account.select_for_update(using_db=using_db).get_or_none(id=account_id, deleted_at=None)
        if account is None or account.status != AccountStatus.ACTIVE:
            raise ForbiddenError('Account is inactive.')

    @staticmethod
    async def _lock_provider(
        account_id: str,
        provider_id: str,
        *,
        expected_version: int,
        using_db: BaseDBAsyncClient,
    ) -> Provider:
        provider = await Provider.select_for_update(using_db=using_db).get_or_none(
            id=provider_id,
            account_id=account_id,
            deleted_at=None,
        )
        if provider is None:
            raise NotfoundError('Provider not found.')
        if not provider.enabled:
            raise BadRequestError('Provider is disabled.')
        if provider.version != expected_version:
            raise BadRequestError('Provider changed during sync. Retry the sync.')
        return provider

    async def _provider_endpoints_with_archived(
        self,
        provider_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> list[_ManagedEndpoint]:
        bindings = await ProviderEndpointBinding.select_for_update(using_db=using_db).filter(provider_id=provider_id)
        endpoint_by_id = await self._endpoint_store.list_snapshots(
            [binding.endpoint_id for binding in bindings],
            using_db=using_db,
        )
        return [
            _ManagedEndpoint(binding=binding, endpoint=endpoint_by_id[binding.endpoint_id])
            for binding in bindings
            if binding.endpoint_id in endpoint_by_id
        ]

    @staticmethod
    def _filter_discovery(provider: Provider, items: list[DiscoveredEndpoint]) -> list[DiscoveredEndpoint]:
        networks = _network_filter(provider.networks)
        vendor = ProviderVendor(provider.vendor)
        filtered: list[DiscoveredEndpoint] = []
        seen: set[str] = set()
        for item in items:
            pair = (item.chain, item.network)
            transport = Transport(item.protocol.value)
            supported = transport in provider_transports(vendor, *pair)
            if not supported or (networks and pair not in networks) or item.external_id in seen:
                continue
            seen.add(item.external_id)
            filtered.append(item)
        return filtered

    async def _create_endpoint(
        self,
        provider: Provider,
        discovered: DiscoveredEndpoint,
        *,
        using_db: BaseDBAsyncClient,
    ) -> _ManagedEndpoint:
        name = await _unique_endpoint_name(
            self._endpoint_store,
            provider.account_id,
            _endpoint_name(provider.name, discovered),
            discovered.external_id,
            using_db=using_db,
        )
        now = datetime_util.now_utc()
        endpoint = await self._endpoint_store.create(
            provider.account_id,
            provider.id,
            _managed_params(name, discovered),
            using_db=using_db,
        )
        binding = await ProviderEndpointBinding.create(
            using_db=using_db,
            endpoint_id=endpoint.id,
            provider_id=provider.id,
            external_id=discovered.external_id,
            last_seen_at=now,
            discovery_status=ProviderEndpointDiscoveryStatus.PRESENT,
            missing_since=None,
        )
        return _ManagedEndpoint(binding=binding, endpoint=endpoint)

    async def _update_endpoint(
        self,
        provider: Provider,
        managed: _ManagedEndpoint,
        discovered: DiscoveredEndpoint,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ProviderEndpointAction | None:
        now = datetime_util.now_utc()
        await (
            ProviderEndpointBinding.filter(endpoint_id=managed.endpoint.id)
            .using_db(using_db)
            .update(
                last_seen_at=now,
                discovery_status=ProviderEndpointDiscoveryStatus.PRESENT,
                missing_since=None,
            )
        )
        managed.binding.last_seen_at = now
        managed.binding.discovery_status = ProviderEndpointDiscoveryStatus.PRESENT
        managed.binding.missing_since = None
        _, change = await self._endpoint_store.reconcile(
            managed.endpoint,
            provider.id,
            _managed_params(managed.endpoint.name, discovered),
            using_db=using_db,
        )
        if change is ManagedEndpointChange.UNCHANGED:
            return None
        return ProviderEndpointAction.RESTORED if change is ManagedEndpointChange.RESTORED else ProviderEndpointAction.UPDATED

    async def _archive_missing(
        self,
        provider: Provider,
        managed_endpoints: list[_ManagedEndpoint],
        seen_external_ids: set[str],
        protected_external_ids: set[str],
        *,
        counters: _SyncCounters,
        using_db: BaseDBAsyncClient,
    ) -> int:
        archived = 0
        missing_since = datetime_util.now_utc()
        for managed in managed_endpoints:
            endpoint = managed.endpoint
            external_id = managed.binding.external_id
            if external_id in seen_external_ids or external_id in protected_external_ids:
                continue
            values: dict[str, object] = {'discovery_status': ProviderEndpointDiscoveryStatus.MISSING}
            if managed.binding.missing_since is None:
                values['missing_since'] = missing_since
            await ProviderEndpointBinding.filter(endpoint_id=endpoint.id).using_db(using_db).update(**values)
            if endpoint.deleted_at is not None:
                continue
            try:
                endpoint = await self._endpoint_store.archive(endpoint, provider.id, using_db=using_db)
            except ManagedEndpointReferencedError as exc:
                counters.skipped += 1
                counters.items.append(
                    ProviderSyncItem(
                        chain=endpoint.chain,
                        network=endpoint.network,
                        action=ProviderEndpointAction.FAILED,
                        endpoint_id=endpoint.id,
                        external_id=external_id,
                        error=str(exc),
                    )
                )
                continue
            counters.items.append(
                ProviderSyncItem(
                    chain=Chain(endpoint.chain),
                    network=Network(endpoint.network),
                    action=ProviderEndpointAction.ARCHIVED,
                    endpoint_id=endpoint.id,
                    external_id=external_id,
                )
            )
            archived += 1
        return archived

    @staticmethod
    async def _update_sync_state(
        provider: Provider,
        *,
        status: ProviderSyncStatus,
        using_db: BaseDBAsyncClient,
    ) -> None:
        await (
            Provider.filter(id=provider.id)
            .using_db(using_db)
            .update(
                last_sync_at=datetime_util.now_utc(),
                last_sync_status=status,
            )
        )

    async def _record_failed(self, provider: Provider, *, error: str) -> ProviderSyncResult:
        counters = _SyncCounters(skipped=1)
        counters.items.append(ProviderSyncItem(action=ProviderEndpointAction.FAILED, error=error))
        async with in_tx() as connection:
            provider = await self._lock_provider(
                provider.account_id,
                provider.id,
                expected_version=provider.version,
                using_db=connection,
            )
            await self._update_sync_state(
                provider,
                status=ProviderSyncStatus.FAILED,
                using_db=connection,
            )
        log.warning(f'Provider sync failed | Account:{provider.account_id} | Provider:{provider.id}')
        return ProviderSyncResult(
            provider_id=provider.id,
            status=ProviderSyncStatus.FAILED,
            created=0,
            updated=0,
            restored=0,
            archived=0,
            skipped=1,
            items=counters.items,
        )


async def _unique_endpoint_name(
    endpoint_store: ManagedEndpointStore,
    account_id: str,
    base_name: str,
    external_id: str,
    *,
    using_db: BaseDBAsyncClient,
) -> str:
    name = base_name.strip().replace(':', '-').replace('/', '-')[:128] or 'provider-endpoint'
    if not await endpoint_store.name_exists(account_id, name, using_db=using_db):
        return name
    suffix = sha256(external_id.encode()).hexdigest()[:8]
    candidate = f'{name[:117]} · {suffix}'
    if not await endpoint_store.name_exists(account_id, candidate, using_db=using_db):
        return candidate
    return f'{name[:104]} · {sha256(f"{external_id}:{name}".encode()).hexdigest()[:21]}'


def _endpoint_name(provider_name: str, discovered: DiscoveredEndpoint) -> str:
    name = provider_name.strip()
    if len(name) > PROVIDER_NAME_LENGTH:
        name = f'{name[: PROVIDER_NAME_LENGTH - 1].rstrip()}…'
    network = f'{discovered.chain.value}-{discovered.network.value}'
    parts = [name, network]
    if discovered.protocol is EndpointProtocol.HTTP_API:
        parts.append('HTTP API')
    return ' · '.join(parts)
