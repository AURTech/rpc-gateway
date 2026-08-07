from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.model.blockchain import CHAIN_CATALOG, Chain, Network, Protocol, validate_chain_network

MAX_TIP_VALUE: Final[int] = (1 << 256) - 1


class TipUnit(StrEnum):
    BLOCK = 'block'
    SLOT = 'slot'


class Finality(StrEnum):
    LATEST = 'latest'
    SAFE = 'safe'
    FINALIZED = 'finalized'


TipDimension = tuple[TipUnit, Finality]

_TIP_DIMENSIONS: Final[Mapping[Protocol, frozenset[TipDimension]]] = MappingProxyType(
    {
        Protocol.EVM: frozenset(
            {
                (TipUnit.BLOCK, Finality.LATEST),
                (TipUnit.BLOCK, Finality.SAFE),
                (TipUnit.BLOCK, Finality.FINALIZED),
            }
        ),
        Protocol.SVM: frozenset(
            {
                (TipUnit.BLOCK, Finality.LATEST),
                (TipUnit.BLOCK, Finality.SAFE),
                (TipUnit.BLOCK, Finality.FINALIZED),
                (TipUnit.SLOT, Finality.LATEST),
                (TipUnit.SLOT, Finality.SAFE),
                (TipUnit.SLOT, Finality.FINALIZED),
            }
        ),
        Protocol.UTXO: frozenset({(TipUnit.BLOCK, Finality.LATEST)}),
        Protocol.TRON: frozenset(
            {
                (TipUnit.BLOCK, Finality.LATEST),
                (TipUnit.BLOCK, Finality.FINALIZED),
            }
        ),
    }
)


def get_tip_dimensions(chain: Chain) -> frozenset[TipDimension]:
    return _TIP_DIMENSIONS[CHAIN_CATALOG[chain].protocol]


def validate_tip_dimension(
    *,
    chain: Chain,
    network: Network,
    unit: TipUnit,
    finality: Finality,
) -> None:
    validate_chain_network(chain, network)
    if (unit, finality) not in get_tip_dimensions(chain):
        raise ValueError(f'{unit.value}/{finality.value} tip is not supported for chain {chain.value}.')


class Tip(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain: Chain
    network: Network
    unit: TipUnit
    finality: Finality
    value: int = Field(ge=0, le=MAX_TIP_VALUE, strict=True)
    observed_at: datetime

    @field_validator('observed_at')
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Tip observation time must include a timezone.')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def validate_dimension(self) -> Self:
        validate_tip_dimension(
            chain=self.chain,
            network=self.network,
            unit=self.unit,
            finality=self.finality,
        )
        return self
