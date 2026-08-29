from typing import Protocol

from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import JsonRpcRoutePlan


class JsonRpcRoutePlanProvider(Protocol):
    async def load(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
        method: str,
    ) -> JsonRpcRoutePlan | None: ...
