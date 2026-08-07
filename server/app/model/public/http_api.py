from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class TronHttpApiFamily(StrEnum):
    WALLET = 'wallet'
    V1 = 'v1'


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicHttpApiRequest:
    method: str
    path: str
    family: TronHttpApiFamily
    path_key: str | None
    headers: Mapping[str, str] = field(default_factory=dict)
    query: Sequence[tuple[str, str]] = field(default_factory=tuple)
    body: bytes = b''


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicHttpApiResult:
    status_code: int
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()
    protocol_matched: bool = True
