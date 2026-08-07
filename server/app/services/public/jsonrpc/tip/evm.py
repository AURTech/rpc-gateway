from datetime import datetime

import msgspec

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse
from app.model.runtime_state.tip import Finality, Tip, TipUnit
from app.services.public.jsonrpc.tip.parse import matches_call, parse_hex_quantity


class _BlockResult(msgspec.Struct):
    number: msgspec.Raw


_BLOCK_DECODER = msgspec.json.Decoder(_BlockResult)


def _block_tag(call: JsonRpcCall) -> Finality | None:
    if not isinstance(call.params, list) or not call.params:
        return None
    tag = call.params[0]
    if tag == 'latest':
        return Finality.LATEST
    if tag == 'safe':
        return Finality.SAFE
    if tag == 'finalized':
        return Finality.FINALIZED
    return None


def extract_tip(
    *,
    chain: Chain,
    network: Network,
    call: JsonRpcCall,
    response: JsonRpcSuccessResponse,
    observed_at: datetime,
) -> Tip | None:
    if CHAIN_CATALOG[chain].protocol is not Protocol.EVM or not matches_call(call, response):
        return None

    finality: Finality | None = Finality.LATEST
    raw_result = response.result
    if call.method == 'eth_getBlockByNumber':
        finality = _block_tag(call)
        if finality is None:
            return None
        try:
            number = _BLOCK_DECODER.decode(raw_result).number
        except msgspec.DecodeError:
            return None
        raw_result = bytes(number)
    elif call.method != 'eth_blockNumber':
        return None

    value = parse_hex_quantity(raw_result)
    if value is None:
        return None
    return Tip(
        chain=chain,
        network=network,
        unit=TipUnit.BLOCK,
        finality=finality,
        value=value,
        observed_at=observed_at,
    )
