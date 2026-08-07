from datetime import datetime

import msgspec

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse
from app.model.runtime_state.tip import Finality, Tip, TipUnit
from app.services.public.jsonrpc.tip.parse import matches_call, parse_uint


class _BlockchainInfoResult(msgspec.Struct):
    blocks: msgspec.Raw


_BLOCKCHAIN_INFO_DECODER = msgspec.json.Decoder(_BlockchainInfoResult)


def extract_tip(
    *,
    chain: Chain,
    network: Network,
    call: JsonRpcCall,
    response: JsonRpcSuccessResponse,
    observed_at: datetime,
) -> Tip | None:
    if CHAIN_CATALOG[chain].protocol is not Protocol.UTXO or not matches_call(call, response):
        return None
    raw_result = response.result
    if call.method == 'getblockchaininfo':
        if call.params not in (None, []):
            return None
        try:
            blocks = _BLOCKCHAIN_INFO_DECODER.decode(raw_result).blocks
        except msgspec.DecodeError:
            return None
        raw_result = bytes(blocks)
    elif call.method != 'getblockcount':
        return None
    value = parse_uint(raw_result)
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
