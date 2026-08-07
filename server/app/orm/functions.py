from typing import Any

from pypika_tortoise.terms import Function as PypikaFunction
from tortoise.expressions import Function


class _PostgresDateTrunc(PypikaFunction):
    def __init__(self, field: Any, unit: str) -> None:
        super().__init__('DATE_TRUNC', unit, field, 'UTC')


class DateTrunc(Function):
    """Truncate a timestamptz field on a stable UTC boundary."""

    database_func = _PostgresDateTrunc
    populate_field_object = True

    def __init__(self, field: str, unit: str) -> None:
        super().__init__(field, unit)
