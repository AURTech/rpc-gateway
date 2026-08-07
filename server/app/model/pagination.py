from typing import Annotated, Literal, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, model_validator

from app.util.datetime import to_utc

DEFAULT_LIST_PAGE_SIZE = 10
MAX_LIST_PAGE_SIZE = 50

ListSort = Literal['ASC', 'DESC']
UtcDateTime = Annotated[AwareDatetime, AfterValidator(to_utc)]


class CreatedAtListParams(BaseModel):
    start_at: UtcDateTime | None = None
    end_at: UtcDateTime | None = None
    sort: ListSort = 'DESC'
    page: int = Field(default=1, ge=1)
    size: int = Field(default=DEFAULT_LIST_PAGE_SIZE, ge=1, le=MAX_LIST_PAGE_SIZE)

    @model_validator(mode='after')
    def validate_time_window(self) -> Self:
        if self.start_at is not None and self.end_at is not None and self.start_at >= self.end_at:
            raise ValueError('start_at must be earlier than end_at.')
        return self


def get_created_at_order(sort: ListSort) -> tuple[str, ...]:
    if sort == 'ASC':
        return ('created_at', 'id')
    return ('-created_at', 'id')
