from datetime import datetime

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse
from app.model.runtime_state.tip import Finality, Tip, TipUnit
from app.services.public.jsonrpc.tip.parse import matches_call, parse_hex_quantity


def extract_tip(
    *,
    chain: Chain,
    network: Network,
    call: JsonRpcCall,
    response: JsonRpcSuccessResponse,
    observed_at: datetime,
) -> Tip | None:
    if (
        CHAIN_CATALOG[chain].protocol is not Protocol.TRON
        or call.method != 'eth_blockNumber'
        or not matches_call(call, response)
    ):
        return None
    value = parse_hex_quantity(response.result)
    if value is None:
        return None
    return Tip(
        chain=chain,
        network=network,
        unit=TipUnit.BLOCK,
        finality=Finality.LATEST,
        value=value,
        observed_at=observed_at,
    )
