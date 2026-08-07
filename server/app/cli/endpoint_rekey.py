import argparse
import asyncio
from dataclasses import dataclass

from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient

from app.core.config import CONF, validate_runtime_security
from app.infra.db import TORTOISE_ORM, in_tx
from app.orm.endpoint import Endpoint
from app.orm.provider import Provider
from app.services.endpoint.crypto import rekey_endpoint_secret, rekey_endpoint_url
from app.services.provider.crypto import rekey_provider_credential


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointRekeyStats:
    endpoints_scanned: int
    urls_changed: int
    auth_secrets_changed: int
    providers_scanned: int
    provider_credentials_changed: int


async def rekey_endpoints(*, apply: bool) -> EndpointRekeyStats:
    """Verify or rekey all endpoint ciphertexts, including soft-deleted rows.

    The apply path locks and updates rows in one transaction. Registry versions
    do not advance because plaintext connection configuration is unchanged.
    """
    async with in_tx() as connection:
        endpoints = await _list_endpoints_including_deleted(connection, lock=apply)
        url_changes = 0
        auth_secret_changes = 0
        for endpoint in endpoints:
            rekeyed_url = rekey_endpoint_url(endpoint.encrypted_url)
            encrypted_auth_secret = endpoint.encrypted_auth_secret
            rekeyed_auth_secret = rekey_endpoint_secret(encrypted_auth_secret) if encrypted_auth_secret is not None else None
            auth_changed = rekeyed_auth_secret != encrypted_auth_secret
            url_changed = rekeyed_url != endpoint.encrypted_url
            url_changes += int(url_changed)
            auth_secret_changes += int(auth_changed)
            if not apply or not (url_changed or auth_changed):
                continue
            values: dict[str, object] = {}
            if url_changed:
                values['encrypted_url'] = rekeyed_url
            if auth_changed:
                values['encrypted_auth_secret'] = rekeyed_auth_secret
            await Endpoint.filter(id=endpoint.id).using_db(connection).update(**values)
        providers = await _list_providers_including_deleted(connection, lock=apply)
        provider_credential_changes = 0
        for provider in providers:
            rekeyed_credential = rekey_provider_credential(provider.encrypted_credential)
            credential_changed = rekeyed_credential != provider.encrypted_credential
            provider_credential_changes += int(credential_changed)
            if apply and credential_changed:
                await Provider.filter(id=provider.id).using_db(connection).update(encrypted_credential=rekeyed_credential)
    return EndpointRekeyStats(
        endpoints_scanned=len(endpoints),
        urls_changed=url_changes,
        auth_secrets_changed=auth_secret_changes,
        providers_scanned=len(providers),
        provider_credentials_changed=provider_credential_changes,
    )


async def _list_endpoints_including_deleted(
    connection: BaseDBAsyncClient,
    *,
    lock: bool,
) -> list[Endpoint]:
    query = Endpoint.all().order_by('created_at', 'id')
    if lock:
        query = query.select_for_update()
    return await query.using_db(connection)


async def _list_providers_including_deleted(
    connection: BaseDBAsyncClient,
    *,
    lock: bool,
) -> list[Provider]:
    query = Provider.all().order_by('created_at', 'id')
    if lock:
        query = query.select_for_update()
    return await query.using_db(connection)


async def _run(*, apply: bool) -> EndpointRekeyStats:
    validate_runtime_security(CONF)
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await rekey_endpoints(apply=apply)
    finally:
        await Tortoise.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify or rekey Endpoint and Provider ciphertexts. Default is dry-run.')
    parser.add_argument('--apply', action='store_true', help='Persist rekeyed Endpoint and Provider ciphertexts.')
    args = parser.parse_args()
    stats = asyncio.run(_run(apply=args.apply))
    action = 'rekeyed' if args.apply else 'would rekey'
    print(
        f'Endpoint crypto {action} | Endpoints:{stats.endpoints_scanned} | URLs:{stats.urls_changed} | '
        f'AuthSecrets:{stats.auth_secrets_changed} | Providers:{stats.providers_scanned} | '
        f'ProviderCredentials:{stats.provider_credentials_changed}'
    )
