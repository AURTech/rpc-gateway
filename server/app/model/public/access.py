from dataclasses import dataclass
from enum import StrEnum

from app.model.account import AccountRole
from app.model.blockchain import Chain, Network
from app.model.transport import Transport


class PublicAccessFailureCode(StrEnum):
    AUTHENTICATION_FAILED = 'authentication_failed'
    GATEWAY_NOT_FOUND = 'gateway_not_found'
    GATEWAY_DISABLED = 'gateway_disabled'
    INTERNAL = 'internal'


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicAccessFailure:
    code: PublicAccessFailureCode


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicGatewayAddress:
    chain: Chain
    network: Network
    transport: Transport


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicGatewayContext:
    account_id: str
    account_role: AccountRole
    app_id: str
    gateway_id: str
    chain: Chain
    network: Network
    transport: Transport


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicGatewayIdentity:
    account_id: str
    account_role: AccountRole
    app_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicGatewaySnapshot:
    gateway_id: str
    enabled: bool
    transports: tuple[Transport, ...]
