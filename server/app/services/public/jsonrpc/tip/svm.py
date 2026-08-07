from datetime import datetime

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse
from app.model.runtime_state.tip import Finality, Tip, TipUnit
from app.services.public.jsonrpc.tip.parse import matches_call, parse_uint


def _commitment(call: JsonRpcCall) -> Finality | None:
    if call.params is None or call.params == []:
        return Finality.FINALIZED
    config: object
    if isinstance(call.params, list):
        if not call.params:
            return Finality.FINALIZED
        config = call.params[0]
    else:
        config = call.params
    if not isinstance(config, dict):
        return None
    commitment = config.get('commitment')
    if commitment is None or commitment == 'finalized':
        return Finality.FINALIZED
    if commitment == 'processed':
        return Finality.LATEST
    if commitment == 'confirmed':
        return Finality.SAFE
    return None


def extract_tip(
    *,
    chain: Chain,
    network: Network,
    call: JsonRpcCall,
    response: JsonRpcSuccessResponse,
    observed_at: datetime,
) -> Tip | None:
    if CHAIN_CATALOG[chain].protocol is not Protocol.SVM or not matches_call(call, response):
        return None
    if call.method == 'getSlot':
        unit = TipUnit.SLOT
    elif call.method == 'getBlockHeight':
        unit = TipUnit.BLOCK
    else:
        return None

    finality = _commitment(call)
    value = parse_uint(response.result)
    if finality is None or value is None:
        return None
    return Tip(
        chain=chain,
        network=network,
        unit=unit,
        finality=finality,
        value=value,
        observed_at=observed_at,
    )
