from collections.abc import Mapping
from typing import Protocol

from app.model.blockchain import Chain, Network
from app.model.http_api_forwarding import HttpApiRoutePlan
from app.model.runtime_state.endpoint.health import EndpointHealth


class HttpApiRoutePlanProvider(Protocol):
    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
    ) -> HttpApiRoutePlan | None: ...


class EndpointHealthReader(Protocol):
    async def get_many(self, endpoints: list[tuple[str, int]]) -> Mapping[str, EndpointHealth | None]: ...
