from typing import Final

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol


def evm_chain_id_map() -> dict[int, tuple[Chain, Network]]:
    result: dict[int, tuple[Chain, Network]] = {}
    for chain, definition in CHAIN_CATALOG.items():
        if definition.protocol is not Protocol.EVM:
            continue
        for network, network_definition in definition.networks.items():
            if network_definition.chain_id is not None:
                result[network_definition.chain_id] = (chain, network)
    return result


EVM_NETWORK_BY_CHAIN_ID: Final = evm_chain_id_map()
