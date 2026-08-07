from typing import Self

from pydantic import Field

from app.model.runtime_state.tip import Tip


class TipObservation(Tip):
    endpoint_id: str = Field(min_length=1, max_length=64)
    endpoint_version: int = Field(ge=1, strict=True)

    @classmethod
    def from_tip(cls, tip: Tip, *, endpoint_id: str, endpoint_version: int) -> Self:
        return cls(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            **tip.model_dump(),
        )
