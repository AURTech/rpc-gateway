from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.model.account import AccountRole, AccountStatus
from app.model.blockchain import Chain, Network
from app.model.public import PublicGatewayIdentity, PublicGatewaySnapshot
from app.orm.application import AppApiKey
from app.orm.gateway import Gateway
from app.services.application.crypto import digest_api_key
from app.services.application.keys import API_KEY_MAX_LENGTH
from app.services.gateway.host import parse_transport_snapshot


@dataclass(frozen=True, slots=True)
class PublicLookupFailure:
    pass


class PublicIdentityLookup(Protocol):
    async def find(self, api_key: str) -> PublicGatewayIdentity | PublicLookupFailure | None: ...


class PublicGatewayLookup(Protocol):
    async def find(
        self,
        *,
        app_id: str,
        chain: Chain,
        network: Network,
    ) -> PublicGatewaySnapshot | PublicLookupFailure | None: ...


class DatabasePublicIdentityLookup:
    async def find(self, api_key: str) -> PublicGatewayIdentity | PublicLookupFailure | None:
        if not api_key or len(api_key) > API_KEY_MAX_LENGTH:
            return None
        try:
            digest = digest_api_key(api_key)
            key = await AppApiKey.filter(api_key_digest=digest, deleted_at=None).select_related('app', 'app__account').first()
            if key is None or key.revoked_at is not None:
                return None
            if key.expires_at is not None and key.expires_at <= datetime.now(UTC):
                return None
            app = key.app
            account = app.account
            if app.deleted_at is not None or not app.enabled:
                return None
            if account.deleted_at is not None or AccountStatus(account.status) is not AccountStatus.ACTIVE:
                return None
            return PublicGatewayIdentity(
                account_id=app.account_id,
                account_role=AccountRole(account.role),
                app_id=key.app_id,
            )
        except Exception:
            return PublicLookupFailure()


class DatabasePublicGatewayLookup:
    async def find(
        self,
        *,
        app_id: str,
        chain: Chain,
        network: Network,
    ) -> PublicGatewaySnapshot | PublicLookupFailure | None:
        try:
            gateway = await Gateway.filter(
                app_id=app_id,
                chain=chain,
                network=network,
                deleted_at=None,
            ).first()
            if gateway is None:
                return None
            if not gateway.enabled:
                return PublicGatewaySnapshot(gateway_id=gateway.id, enabled=False, transports=())
            transports = parse_transport_snapshot(chain, network, gateway.transport_types)
            return PublicGatewaySnapshot(gateway_id=gateway.id, enabled=True, transports=transports)
        except Exception:
            return PublicLookupFailure()
