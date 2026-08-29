from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointAuthType, EndpointProtocol
from app.model.provider import ProviderSettingsParams, ProviderVendor


class ProviderDiscoveryError(Exception):
    pass


AccountActiveCheck = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderDiscoveryConfig:
    credential: str = field(repr=False)
    settings: ProviderSettingsParams


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveredEndpoint:
    external_id: str
    chain: Chain
    network: Network
    url: str = field(repr=False)
    protocol: EndpointProtocol = EndpointProtocol.JSONRPC
    auth_type: EndpointAuthType = EndpointAuthType.NONE
    auth_name: str | None = None
    auth_secret: str | None = field(default=None, repr=False)
    legacy_external_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderDiscoveryFailure:
    external_id: str | None
    error: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderDiscovery:
    items: list[DiscoveredEndpoint]
    failures: list[ProviderDiscoveryFailure] = field(default_factory=list)
    complete: bool = True


class ProviderAdapter(Protocol):
    vendor: ProviderVendor

    async def discover(
        self,
        config: ProviderDiscoveryConfig,
        check_account_active: AccountActiveCheck,
    ) -> ProviderDiscovery: ...
