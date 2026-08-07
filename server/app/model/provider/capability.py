from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.model.blockchain import CHAIN_CATALOG, Chain, Network
from app.model.provider_state import ProviderVendor
from app.model.transport import Transport

ProviderNetwork = tuple[Chain, Network]


def _jsonrpc(*networks: ProviderNetwork) -> dict[ProviderNetwork, frozenset[Transport]]:
    return {network: frozenset({Transport.JSONRPC}) for network in networks}


_EVM_NETWORKS: Final[tuple[ProviderNetwork, ...]] = (
    (Chain.ETHEREUM, Network.MAINNET),
    (Chain.ETHEREUM, Network.SEPOLIA),
    (Chain.POLYGON, Network.MAINNET),
    (Chain.POLYGON, Network.AMOY),
    (Chain.BSC, Network.MAINNET),
    (Chain.BSC, Network.TESTNET),
    (Chain.ARBITRUM, Network.MAINNET),
    (Chain.ARBITRUM, Network.SEPOLIA),
    (Chain.OPTIMISM, Network.MAINNET),
    (Chain.OPTIMISM, Network.SEPOLIA),
    (Chain.BASE, Network.MAINNET),
    (Chain.BASE, Network.SEPOLIA),
)

_NON_EVM_NETWORKS: Final[tuple[ProviderNetwork, ...]] = (
    (Chain.SOLANA, Network.MAINNET_BETA),
    (Chain.SOLANA, Network.DEVNET),
    (Chain.BITCOIN, Network.MAINNET),
    (Chain.BITCOIN, Network.TESTNET),
    (Chain.LITECOIN, Network.MAINNET),
    (Chain.LITECOIN, Network.TESTNET),
)

_TENDERLY_NETWORKS: Final = tuple(network for network in _EVM_NETWORKS if network[0] is not Chain.BSC)
_TRON_TRANSPORTS: Final = frozenset({Transport.JSONRPC, Transport.HTTP_API})

_ALCHEMY = _jsonrpc(*_EVM_NETWORKS, *_NON_EVM_NETWORKS)
_ALCHEMY[(Chain.TRON, Network.MAINNET)] = _TRON_TRANSPORTS
_ALCHEMY[(Chain.TRON, Network.NILE)] = _TRON_TRANSPORTS

_QUICKNODE = dict(_ALCHEMY)

_CHAINSTACK = _jsonrpc(
    *_EVM_NETWORKS,
    (Chain.SOLANA, Network.MAINNET_BETA),
    (Chain.SOLANA, Network.DEVNET),
    (Chain.BITCOIN, Network.MAINNET),
    (Chain.BITCOIN, Network.TESTNET),
    (Chain.LITECOIN, Network.MAINNET),
)
_CHAINSTACK[(Chain.TRON, Network.MAINNET)] = _TRON_TRANSPORTS
_CHAINSTACK[(Chain.TRON, Network.NILE)] = _TRON_TRANSPORTS

_DRPC = _jsonrpc(
    *_EVM_NETWORKS,
    (Chain.SOLANA, Network.MAINNET_BETA),
    (Chain.SOLANA, Network.DEVNET),
    (Chain.BITCOIN, Network.MAINNET),
    (Chain.TRON, Network.MAINNET),
)

_TENDERLY = _jsonrpc(*_TENDERLY_NETWORKS)

PROVIDER_CAPABILITIES: Final[Mapping[ProviderVendor, Mapping[ProviderNetwork, frozenset[Transport]]]] = MappingProxyType(
    {
        ProviderVendor.ALCHEMY: MappingProxyType(_ALCHEMY),
        ProviderVendor.QUICKNODE: MappingProxyType(_QUICKNODE),
        ProviderVendor.CHAINSTACK: MappingProxyType(_CHAINSTACK),
        ProviderVendor.DRPC: MappingProxyType(_DRPC),
        ProviderVendor.TENDERLY: MappingProxyType(_TENDERLY),
    }
)


def provider_networks(vendor: ProviderVendor) -> frozenset[ProviderNetwork]:
    return frozenset(PROVIDER_CAPABILITIES[vendor])


def provider_transports(vendor: ProviderVendor, chain: Chain, network: Network) -> frozenset[Transport]:
    return PROVIDER_CAPABILITIES[vendor].get((chain, network), frozenset())


def _validate_capabilities() -> None:
    for capabilities in PROVIDER_CAPABILITIES.values():
        for chain, network in capabilities:
            if network not in CHAIN_CATALOG[chain].networks:
                raise ValueError(f'Provider capability contains unsupported network {chain.value}:{network.value}.')


_validate_capabilities()
