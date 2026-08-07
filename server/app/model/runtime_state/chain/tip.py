from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.model.blockchain import Chain, Network
from app.model.runtime_state.tip import Finality, TipUnit, validate_tip_dimension


class ChainTip(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain: Chain
    network: Network
    unit: TipUnit
    finality: Finality
    value: int = Field(ge=0, strict=True)
    source_count: int = Field(ge=3, le=10_000, strict=True)
    observed_at: datetime
    computed_at: datetime
    valid_until: datetime

    @field_validator('observed_at', 'computed_at', 'valid_until')
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Chain tip times must include a timezone.')
        return value.astimezone(UTC)

    @model_validator(mode='after')
    def validate_tip(self) -> Self:
        validate_tip_dimension(
            chain=self.chain,
            network=self.network,
            unit=self.unit,
            finality=self.finality,
        )
        if self.valid_until <= self.computed_at:
            raise ValueError('Chain tip validity must be later than its computation time.')
        return self
