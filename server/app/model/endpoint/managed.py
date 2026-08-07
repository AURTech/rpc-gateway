from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.model.blockchain import Chain, Network
from app.model.endpoint.endpoint import EndpointCreateAuthParams, EndpointItem, EndpointProtocol


class ManagedEndpointValidationError(Exception):
    pass


class ManagedEndpointReferencedError(Exception):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ManagedEndpointParams:
    name: str
    chain: Chain
    network: Network
    protocol: EndpointProtocol
    url: str
    auth: EndpointCreateAuthParams
    enabled: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class ManagedEndpointSnapshot:
    id: str
    account_id: str
    name: str
    chain: Chain
    network: Network
    protocol: EndpointProtocol
    enabled: bool
    version: int
    deleted_at: datetime | None
    modified_at: datetime


class ManagedEndpointChange(StrEnum):
    UNCHANGED = 'unchanged'
    UPDATED = 'updated'
    RESTORED = 'restored'


@dataclass(frozen=True, slots=True, kw_only=True)
class ManagedEndpointItem:
    endpoint: EndpointItem
    deleted_at: datetime | None
