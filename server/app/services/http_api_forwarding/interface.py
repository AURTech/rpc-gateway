from typing import Protocol

from app.model.blockchain import Chain, Network
from app.model.http_api_forwarding import HttpApiRoutePlan


class HttpApiRoutePlanProvider(Protocol):
    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
    ) -> HttpApiRoutePlan | None: ...
