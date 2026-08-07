from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final
from typing import Protocol as TypingProtocol

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol
from app.model.endpoint import EndpointDescriptor
from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse
from app.model.runtime_state.endpoint.tip import TipObservation
from app.model.runtime_state.tip import Tip
from app.services.public.jsonrpc.tip import evm, svm, tron, utxo


class TipExtractor(TypingProtocol):
    def __call__(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
        response: JsonRpcSuccessResponse,
        observed_at: datetime,
    ) -> Tip | None: ...


_EXTRACTORS: Final[Mapping[Protocol, TipExtractor]] = MappingProxyType(
    {
        Protocol.EVM: evm.extract_tip,
        Protocol.SVM: svm.extract_tip,
        Protocol.UTXO: utxo.extract_tip,
        Protocol.TRON: tron.extract_tip,
    }
)


def extract_tip(
    *,
    chain: Chain,
    network: Network,
    call: JsonRpcCall,
    response: JsonRpcSuccessResponse,
    observed_at: datetime,
) -> Tip | None:
    extractor = _EXTRACTORS[CHAIN_CATALOG[chain].protocol]
    return extractor(
        chain=chain,
        network=network,
        call=call,
        response=response,
        observed_at=observed_at,
    )


def extract_tip_observation(
    *,
    endpoint: EndpointDescriptor,
    call: JsonRpcCall,
    response: JsonRpcSuccessResponse,
    observed_at: datetime,
) -> TipObservation | None:
    tip = extract_tip(
        chain=endpoint.chain,
        network=endpoint.network,
        call=call,
        response=response,
        observed_at=observed_at,
    )
    if tip is None:
        return None
    return TipObservation.from_tip(
        tip,
        endpoint_id=endpoint.id,
        endpoint_version=endpoint.version,
    )


__all__ = ['extract_tip', 'extract_tip_observation']
