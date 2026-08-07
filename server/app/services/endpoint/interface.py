from typing import Protocol

from tortoise.backends.base.client import BaseDBAsyncClient

from app.model.blockchain import Chain, Network
from app.model.endpoint.access import EndpointAccessResult, EndpointDescriptor, EndpointRequest
from app.model.endpoint.endpoint import EndpointProtocol
from app.model.endpoint.managed import (
    ManagedEndpointChange,
    ManagedEndpointItem,
    ManagedEndpointParams,
    ManagedEndpointSnapshot,
)


class EndpointAccess(Protocol):
    async def get_descriptor(self, account_id: str, endpoint_id: str) -> EndpointDescriptor | None: ...

    async def list_descriptors(
        self,
        account_id: str,
        *,
        chain: Chain | None = None,
        network: Network | None = None,
        protocol: EndpointProtocol | None = None,
        enabled: bool | None = None,
    ) -> list[EndpointDescriptor]: ...

    async def execute(self, account_id: str, endpoint_id: str, request: EndpointRequest) -> EndpointAccessResult: ...


class EndpointRouteReferenceLookup(Protocol):
    async def referenced_endpoint_ids(
        self,
        endpoint_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> set[str]: ...


class ManagedEndpointStore(Protocol):
    async def validate_url(self, url: str) -> None: ...

    async def name_exists(self, account_id: str, name: str, *, using_db: BaseDBAsyncClient) -> bool: ...

    async def list_snapshots(
        self,
        endpoint_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> dict[str, ManagedEndpointSnapshot]: ...

    async def create(
        self,
        account_id: str,
        actor_id: str,
        params: ManagedEndpointParams,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ManagedEndpointSnapshot: ...

    async def reconcile(
        self,
        snapshot: ManagedEndpointSnapshot,
        actor_id: str,
        params: ManagedEndpointParams,
        *,
        using_db: BaseDBAsyncClient,
    ) -> tuple[ManagedEndpointSnapshot, ManagedEndpointChange]: ...

    async def archive(
        self,
        snapshot: ManagedEndpointSnapshot,
        actor_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ManagedEndpointSnapshot: ...

    async def detach(
        self,
        snapshot: ManagedEndpointSnapshot,
        actor_id: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> ManagedEndpointSnapshot: ...

    async def list_items(self, account_id: str, endpoint_ids: list[str]) -> dict[str, ManagedEndpointItem]: ...
