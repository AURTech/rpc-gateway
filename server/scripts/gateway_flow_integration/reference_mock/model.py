from dataclasses import dataclass
from enum import StrEnum

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class ReferenceChain(StrEnum):
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


class ReferenceBehavior(StrEnum):
    GOOD = 'good'
    BAD = 'bad'
    UNAVAILABLE = 'unavailable'
    INVALID = 'invalid'
    TIMEOUT = 'timeout'
    WRONG_ID = 'wrong-id'
    WRONG_HEIGHT = 'wrong-height'


class ReferenceTransport(StrEnum):
    JSONRPC = 'jsonrpc'
    HTTP_API = 'http_api'


EVM_CHAINS = frozenset(
    {
        ReferenceChain.ETHEREUM,
        ReferenceChain.POLYGON,
        ReferenceChain.BSC,
        ReferenceChain.ARBITRUM,
        ReferenceChain.OPTIMISM,
        ReferenceChain.BASE,
    }
)
UTXO_CHAINS = frozenset({ReferenceChain.BITCOIN, ReferenceChain.LITECOIN})


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestFacts:
    transport: ReferenceTransport
    chain: ReferenceChain
    source: int
    host: str | None
    peer_host: str | None
    method: str
    request_id: str | int | None
    params: JsonValue
    head: int
    target_height: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceReply:
    status_code: int
    body: bytes
    media_type: str
    response_id: str | int | None
    payload: JsonValue | None


class UnsupportedReferenceRequestError(ValueError):
    pass
