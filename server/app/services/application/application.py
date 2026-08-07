from dataclasses import dataclass
from datetime import datetime, timedelta

from fastlog import log
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from app.core.errors import BadRequestError, NotfoundError, UnavailableError
from app.infra.db import in_tx
from app.model.application import (
    AppAuditAction,
    AppItem,
    AppKeyItem,
    AppKeyList,
    AppKeyState,
    AppList,
    AppListItem,
    CreateAppParams,
    CreatedApp,
    CreatedAppKey,
    DeletedApp,
    UpdateAppParams,
)
from app.model.blockchain import CHAIN_CATALOG, Chain
from app.model.pagination import DEFAULT_LIST_PAGE_SIZE, ListSort, get_created_at_order
from app.model.transport import Transport
from app.orm.application import App, AppApiKey
from app.orm.gateway import Gateway
from app.orm.http_api_route import HttpApiRoute
from app.orm.jsonrpc_route import JsonRpcRoute, JsonRpcRouteScope
from app.orm.mixin import NANOIDField
from app.services.application.audit import write_audit_event
from app.services.application.crypto import AppKeyCryptoError, decrypt_api_key, digest_api_key, encrypt_api_key
from app.services.application.keys import API_KEY_ROTATION_GRACE_SECONDS, generate_api_key
from app.util import datetime as datetime_util

_KEY_CREATE_RETRIES = 5


@dataclass(frozen=True, slots=True)
class _NewAppKey:
    id: str
    api_key: str
    digest: str
    encrypted: str


class ApplicationManager:
    @staticmethod
    async def create_app(account_id: str, actor_id: str, params: CreateAppParams) -> CreatedApp:
        app_id = NANOIDField.nanoid()
        try:
            new_key = await ApplicationManager._build_key(app_id)
            async with in_tx() as connection:
                app = await App.create(
                    using_db=connection,
                    id=app_id,
                    account_id=account_id,
                    name=params.name,
                    enabled=params.enabled,
                    version=1,
                )
                await AppApiKey.create(
                    using_db=connection,
                    id=new_key.id,
                    app_id=app.id,
                    api_key_digest=new_key.digest,
                    encrypted_api_key=new_key.encrypted,
                )
                gateways = [
                    Gateway(
                        app_id=app.id,
                        name=f'{chain.value}-{network.value}',
                        chain=chain,
                        network=network,
                        transport_types=[transport.value for transport in network_definition.gateway_transports],
                        enabled=True,
                        version=1,
                    )
                    for chain, chain_definition in CHAIN_CATALOG.items()
                    for network, network_definition in chain_definition.networks.items()
                ]
                await Gateway.bulk_create(gateways, using_db=connection)
                routes = [JsonRpcRoute(id=NANOIDField.nanoid(), gateway_id=gateway.id) for gateway in gateways]
                await JsonRpcRoute.bulk_create(routes, using_db=connection)
                scopes = [JsonRpcRouteScope(route_id=route.id, gateway_id=route.gateway_id, method='') for route in routes]
                await JsonRpcRouteScope.bulk_create(scopes, using_db=connection)
                http_api_routes = [
                    HttpApiRoute(gateway_id=gateway.id)
                    for gateway in gateways
                    if Transport.HTTP_API.value in gateway.transport_types
                ]
                await HttpApiRoute.bulk_create(http_api_routes, using_db=connection)
                await write_audit_event(
                    app.id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='app',
                    resource_id=app.id,
                    action=AppAuditAction.CREATED,
                    previous_version=None,
                    new_version=1,
                    changed_fields=['name', 'enabled'],
                    using_db=connection,
                )
                await write_audit_event(
                    app.id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='api_key',
                    resource_id=new_key.id,
                    action=AppAuditAction.API_KEY_CREATED,
                    previous_version=None,
                    new_version=None,
                    changed_fields=[],
                    using_db=connection,
                )
        except IntegrityError as exc:
            log.warning(f'App name already exists | Account:{account_id}')
            raise BadRequestError('App name already exists.') from exc
        except AppKeyCryptoError as exc:
            log.warning(f'App API Key encryption is unavailable | Account:{account_id}')
            raise UnavailableError('App API Key encryption is unavailable.') from exc
        log.info(f'App {app.id} created | Account:{account_id} | Gateways:{len(gateways)}')
        item = ApplicationManager._to_item(app)
        return CreatedApp(**item.model_dump(), api_key_id=new_key.id, api_key=new_key.api_key)

    @staticmethod
    async def list_apps(
        account_id: str,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        sort: ListSort = 'DESC',
        page: int = 1,
        size: int = DEFAULT_LIST_PAGE_SIZE,
    ) -> AppList:
        query = App.filter(account_id=account_id, deleted_at=None)
        if search:
            query = query.filter(Q(name__icontains=search.strip()) | Q(id__icontains=search.strip()))
        if enabled is not None:
            query = query.filter(enabled=enabled)
        if start_at is not None:
            query = query.filter(created_at__gte=start_at)
        if end_at is not None:
            query = query.filter(created_at__lt=end_at)
        total = await query.count()
        rows = await query.order_by(*get_created_at_order(sort)).offset((page - 1) * size).limit(size)
        app_ids = [row.id for row in rows]
        gateway_rows = await Gateway.filter(app_id__in=app_ids, deleted_at=None).only('app_id', 'chain', 'enabled')
        gateways_by_app: dict[str, list[Gateway]] = {app_id: [] for app_id in app_ids}
        for gateway in gateway_rows:
            gateways_by_app[gateway.app_id].append(gateway)
        items = [ApplicationManager._to_list_item(row, gateways_by_app[row.id]) for row in rows]
        max_page = (total + size - 1) // size if size else 0
        return AppList(page=page, size=size, total=total, max_page=max_page, items=items)

    @staticmethod
    async def get_app(account_id: str, app_id: str) -> AppItem:
        app = await ApplicationManager._get_app(account_id, app_id)
        return ApplicationManager._to_item(app)

    @staticmethod
    async def update_app(account_id: str, actor_id: str, app_id: str, params: UpdateAppParams) -> AppItem:
        try:
            async with in_tx() as connection:
                app = await App.select_for_update(using_db=connection).get_or_none(
                    id=app_id,
                    account_id=account_id,
                    deleted_at=None,
                )
                if app is None:
                    raise NotfoundError('App not found.')
                if app.version != params.expected_version:
                    raise BadRequestError('App version conflict. Reload the App before saving.')
                values = params.model_dump(exclude={'expected_version'}, exclude_unset=True)
                changed_fields = [name for name, value in values.items() if value != getattr(app, name)]
                if not changed_fields:
                    return ApplicationManager._to_item(app)
                previous_version = app.version
                new_version = previous_version + 1
                values['version'] = new_version
                values['modified_at'] = datetime_util.next_utc_timestamp(app.modified_at)
                await App.filter(id=app.id).using_db(connection).update(**values)
                app.update_from_dict(values)
                await write_audit_event(
                    app.id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='app',
                    resource_id=app.id,
                    action=AppAuditAction.UPDATED,
                    previous_version=previous_version,
                    new_version=new_version,
                    changed_fields=changed_fields,
                    using_db=connection,
                )
        except IntegrityError as exc:
            log.warning(f'App name already exists | Account:{account_id} | App:{app_id}')
            raise BadRequestError('App name already exists.') from exc
        log.info(f'App {app_id} updated | Account:{account_id} | Version:{app.version}')
        return ApplicationManager._to_item(app)

    @staticmethod
    async def delete_app(account_id: str, actor_id: str, app_id: str) -> DeletedApp:
        async with in_tx() as connection:
            app = await App.select_for_update(using_db=connection).get_or_none(
                id=app_id,
                account_id=account_id,
                deleted_at=None,
            )
            if app is None:
                raise NotfoundError('App not found.')
            previous_version = app.version
            new_version = previous_version + 1
            deleted_at = datetime_util.next_utc_timestamp(app.modified_at)
            await write_audit_event(
                app.id,
                account_id=account_id,
                actor_id=actor_id,
                resource_type='app',
                resource_id=app.id,
                action=AppAuditAction.DELETED,
                previous_version=previous_version,
                new_version=new_version,
                changed_fields=['deleted_at', 'enabled'],
                using_db=connection,
            )
            await (
                App.filter(id=app.id)
                .using_db(connection)
                .update(
                    enabled=False,
                    version=new_version,
                    deleted_at=deleted_at,
                    modified_at=deleted_at,
                )
            )
            await (
                Gateway.filter(app_id=app.id, deleted_at=None)
                .using_db(connection)
                .update(
                    enabled=False,
                    deleted_at=deleted_at,
                    modified_at=deleted_at,
                )
            )
            await (
                AppApiKey.filter(app_id=app.id, deleted_at=None)
                .using_db(connection)
                .update(
                    revoked_at=deleted_at,
                    deleted_at=deleted_at,
                    modified_at=deleted_at,
                )
            )
        log.info(f'App {app_id} deleted | Account:{account_id}')
        return DeletedApp(id=app_id, version=new_version, deleted=True)

    @staticmethod
    async def list_keys(account_id: str, app_id: str) -> AppKeyList:
        await ApplicationManager._get_app(account_id, app_id)
        rows = await AppApiKey.filter(app_id=app_id, deleted_at=None).order_by('-created_at', '-id')
        now = datetime_util.now_utc()
        try:
            items = [ApplicationManager._to_key_item(row, now=now) for row in rows]
        except AppKeyCryptoError as exc:
            log.warning(f'App API Key decryption is unavailable | Account:{account_id} | App:{app_id}')
            raise UnavailableError('App API Keys are unavailable.') from exc
        return AppKeyList(total=len(rows), items=items)

    @staticmethod
    async def rotate_key(account_id: str, actor_id: str, app_id: str) -> CreatedAppKey:
        try:
            new_key = await ApplicationManager._build_key(app_id)
            async with in_tx() as connection:
                app = await App.select_for_update(using_db=connection).get_or_none(
                    id=app_id,
                    account_id=account_id,
                    deleted_at=None,
                )
                if app is None:
                    raise NotfoundError('App not found.')
                now = datetime_util.now_utc()
                active_keys = await AppApiKey.select_for_update(using_db=connection).filter(
                    app_id=app_id,
                    deleted_at=None,
                    revoked_at=None,
                    expires_at=None,
                )
                for key in active_keys:
                    key.expires_at = now + timedelta(seconds=API_KEY_ROTATION_GRACE_SECONDS)
                    await key.save(using_db=connection, update_fields=['expires_at', 'modified_at'])
                key = await AppApiKey.create(
                    using_db=connection,
                    id=new_key.id,
                    app_id=app_id,
                    api_key_digest=new_key.digest,
                    encrypted_api_key=new_key.encrypted,
                )
                await write_audit_event(
                    app.id,
                    account_id=account_id,
                    actor_id=actor_id,
                    resource_type='api_key',
                    resource_id=key.id,
                    action=AppAuditAction.API_KEY_CREATED,
                    previous_version=None,
                    new_version=None,
                    changed_fields=[],
                    using_db=connection,
                )
        except AppKeyCryptoError as exc:
            log.warning(f'App API Key encryption is unavailable | Account:{account_id} | App:{app_id}')
            raise UnavailableError('App API Key encryption is unavailable.') from exc
        log.info(f'App API Key rotated | Account:{account_id} | App:{app_id} | Key:{key.id}')
        item = ApplicationManager._to_key_item(key, now=datetime_util.now_utc(), api_key=new_key.api_key)
        return CreatedAppKey(**item.model_dump())

    @staticmethod
    async def revoke_key(account_id: str, actor_id: str, app_id: str, key_id: str) -> AppKeyItem:
        try:
            async with in_tx() as connection:
                app = await App.select_for_update(using_db=connection).get_or_none(
                    id=app_id,
                    account_id=account_id,
                    deleted_at=None,
                )
                if app is None:
                    raise NotfoundError('App not found.')
                key = await AppApiKey.select_for_update(using_db=connection).get_or_none(
                    id=key_id,
                    app_id=app_id,
                    deleted_at=None,
                )
                if key is None:
                    raise NotfoundError('App API Key not found.')
                api_key = decrypt_api_key(key.encrypted_api_key, app_id=app_id, key_id=key.id)
                if key.revoked_at is None:
                    key.revoked_at = datetime_util.now_utc()
                    await key.save(using_db=connection, update_fields=['revoked_at', 'modified_at'])
                    await write_audit_event(
                        app.id,
                        account_id=account_id,
                        actor_id=actor_id,
                        resource_type='api_key',
                        resource_id=key.id,
                        action=AppAuditAction.API_KEY_REVOKED,
                        previous_version=None,
                        new_version=None,
                        changed_fields=['revoked_at'],
                        using_db=connection,
                    )
        except AppKeyCryptoError as exc:
            log.warning(f'App API Key decryption is unavailable | Account:{account_id} | App:{app_id} | Key:{key_id}')
            raise UnavailableError('App API Key is unavailable.') from exc
        log.info(f'App API Key revoked | Account:{account_id} | App:{app_id} | Key:{key_id}')
        return ApplicationManager._to_key_item(key, now=datetime_util.now_utc(), api_key=api_key)

    @staticmethod
    async def _build_key(app_id: str) -> _NewAppKey:
        for _ in range(_KEY_CREATE_RETRIES):
            key_id = NANOIDField.nanoid()
            api_key = generate_api_key()
            digest = digest_api_key(api_key)
            if await AppApiKey.filter(api_key_digest=digest).exists():
                continue
            encrypted = encrypt_api_key(api_key, app_id=app_id, key_id=key_id)
            return _NewAppKey(id=key_id, api_key=api_key, digest=digest, encrypted=encrypted)
        raise BadRequestError('Could not generate a unique App API Key.')

    @staticmethod
    async def _get_app(account_id: str, app_id: str) -> App:
        app = await App.filter(id=app_id, account_id=account_id, deleted_at=None).first()
        if app is None:
            raise NotfoundError('App not found.')
        return app

    @staticmethod
    def _to_item(app: App) -> AppItem:
        return AppItem(
            id=app.id,
            name=app.name,
            enabled=app.enabled,
            provider_id=app.provider_id,
            version=app.version,
            created_at=app.created_at,
            modified_at=app.modified_at,
        )

    @staticmethod
    def _to_list_item(app: App, gateways: list[Gateway]) -> AppListItem:
        chains = list(dict.fromkeys(Chain(gateway.chain) for gateway in gateways))
        item = ApplicationManager._to_item(app)
        return AppListItem(
            **item.model_dump(),
            chains=chains,
            gateway_count=len(gateways),
            enabled_gateway_count=sum(gateway.enabled for gateway in gateways),
        )

    @staticmethod
    def _key_state(key: AppApiKey, *, now: datetime) -> AppKeyState:
        if key.revoked_at is not None:
            return AppKeyState.REVOKED
        if key.expires_at is not None:
            return AppKeyState.EXPIRED if key.expires_at <= now else AppKeyState.GRACE
        return AppKeyState.ACTIVE

    @staticmethod
    def _to_key_item(key: AppApiKey, *, now: datetime, api_key: str | None = None) -> AppKeyItem:
        state = ApplicationManager._key_state(key, now=now)
        value = api_key if api_key is not None else decrypt_api_key(key.encrypted_api_key, app_id=key.app_id, key_id=key.id)
        return AppKeyItem(
            id=key.id,
            api_key=value,
            state=state,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            created_at=key.created_at,
        )
