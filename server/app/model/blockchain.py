from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.model.transport import Transport


class Chain(StrEnum):
    ETHEREUM = 'ethereum'
    POLYGON = 'polygon'
    BSC = 'bsc'
    ARBITRUM = 'arbitrum'
    OPTIMISM = 'optimism'
    BASE = 'base'
    SOLANA = 'solana'
    BITCOIN = 'bitcoin'
    LITECOIN = 'litecoin'
    TRON = 'tron'


class Network(StrEnum):
    MAINNET = 'mainnet'
    MAINNET_BETA = 'mainnet-beta'
    SEPOLIA = 'sepolia'
    AMOY = 'amoy'
    TESTNET = 'testnet'
    DEVNET = 'devnet'
    NILE = 'nile'


class Protocol(StrEnum):
    EVM = 'evm'
    SVM = 'svm'
    UTXO = 'utxo'
    TRON = 'tron'

    @property
    def label(self) -> str:
        return _PROTOCOL_LABELS[self]


class Token(StrEnum):
    ETH = 'eth'
    POL = 'pol'
    BNB = 'bnb'
    SOL = 'sol'
    BTC = 'btc'
    LTC = 'ltc'
    TRX = 'trx'

    @property
    def label(self) -> str:
        return _TOKEN_LABELS[self]


_PROTOCOL_LABELS: Final[Mapping[Protocol, str]] = MappingProxyType(
    {
        Protocol.EVM: 'EVM',
        Protocol.SVM: 'SVM',
        Protocol.UTXO: 'UTXO',
        Protocol.TRON: 'TRON',
    }
)

_TOKEN_LABELS: Final[Mapping[Token, str]] = MappingProxyType(
    {
        Token.ETH: 'ETH',
        Token.POL: 'POL',
        Token.BNB: 'BNB',
        Token.SOL: 'SOL',
        Token.BTC: 'BTC',
        Token.LTC: 'LTC',
        Token.TRX: 'TRX',
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkDefinition:
    label: str
    chain_id: int | None
    gateway_transports: tuple[Transport, ...] = (Transport.JSONRPC,)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChainDefinition:
    label: str
    protocol: Protocol
    token: Token
    networks: Mapping[Network, NetworkDefinition]


CHAIN_CATALOG: Final[Mapping[Chain, ChainDefinition]] = MappingProxyType(
    {
        Chain.ETHEREUM: ChainDefinition(
            label='Ethereum',
            protocol=Protocol.EVM,
            token=Token.ETH,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=1),
                    Network.SEPOLIA: NetworkDefinition(label='Sepolia', chain_id=11155111),
                }
            ),
        ),
        Chain.POLYGON: ChainDefinition(
            label='Polygon',
            protocol=Protocol.EVM,
            token=Token.POL,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=137),
                    Network.AMOY: NetworkDefinition(label='Amoy', chain_id=80002),
                }
            ),
        ),
        Chain.BSC: ChainDefinition(
            label='BNB Smart Chain',
            protocol=Protocol.EVM,
            token=Token.BNB,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=56),
                    Network.TESTNET: NetworkDefinition(label='Testnet', chain_id=97),
                }
            ),
        ),
        Chain.ARBITRUM: ChainDefinition(
            label='Arbitrum',
            protocol=Protocol.EVM,
            token=Token.ETH,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=42161),
                    Network.SEPOLIA: NetworkDefinition(label='Sepolia', chain_id=421614),
                }
            ),
        ),
        Chain.OPTIMISM: ChainDefinition(
            label='Optimism',
            protocol=Protocol.EVM,
            token=Token.ETH,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=10),
                    Network.SEPOLIA: NetworkDefinition(label='Sepolia', chain_id=11155420),
                }
            ),
        ),
        Chain.BASE: ChainDefinition(
            label='Base',
            protocol=Protocol.EVM,
            token=Token.ETH,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=8453),
                    Network.SEPOLIA: NetworkDefinition(label='Sepolia', chain_id=84532),
                }
            ),
        ),
        Chain.SOLANA: ChainDefinition(
            label='Solana',
            protocol=Protocol.SVM,
            token=Token.SOL,
            networks=MappingProxyType(
                {
                    # Display label only; the wire value stays `mainnet-beta`.
                    Network.MAINNET_BETA: NetworkDefinition(label='Mainnet', chain_id=None),
                    Network.DEVNET: NetworkDefinition(label='Devnet', chain_id=None),
                }
            ),
        ),
        Chain.BITCOIN: ChainDefinition(
            label='Bitcoin',
            protocol=Protocol.UTXO,
            token=Token.BTC,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=None),
                    Network.TESTNET: NetworkDefinition(label='Testnet', chain_id=None),
                }
            ),
        ),
        Chain.LITECOIN: ChainDefinition(
            label='Litecoin',
            protocol=Protocol.UTXO,
            token=Token.LTC,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(label='Mainnet', chain_id=None),
                    Network.TESTNET: NetworkDefinition(label='Testnet', chain_id=None),
                }
            ),
        ),
        Chain.TRON: ChainDefinition(
            label='TRON',
            protocol=Protocol.TRON,
            token=Token.TRX,
            networks=MappingProxyType(
                {
                    Network.MAINNET: NetworkDefinition(
                        label='Mainnet',
                        chain_id=728126428,
                        gateway_transports=(Transport.JSONRPC, Transport.HTTP_API),
                    ),
                    Network.NILE: NetworkDefinition(
                        label='Nile',
                        chain_id=3448148188,
                        gateway_transports=(Transport.JSONRPC, Transport.HTTP_API),
                    ),
                }
            ),
        ),
    }
)


def validate_chain_network(chain: Chain, network: Network) -> None:
    if network not in CHAIN_CATALOG[chain].networks:
        raise ValueError(f'Network {network.value} is not supported for chain {chain.value}.')
