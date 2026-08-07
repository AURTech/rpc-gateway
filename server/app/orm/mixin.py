import string
from typing import Any

from nanoid import generate
from tortoise import fields, models


class NANOIDField(fields.Field[str]):
    """
    NANOID Field

    If used as a primary key, it will auto-generate a NANOID by default.
    """

    field_type = str
    SQL_TYPE = 'CHAR(21)'

    def __init__(self, **kwargs: Any) -> None:
        if kwargs.get('primary_key') and 'default' not in kwargs:
            kwargs['default'] = self.nanoid
        super().__init__(**kwargs)

    @classmethod
    def nanoid(cls) -> str:
        alphabet = string.digits + string.ascii_letters
        return generate(size=21, alphabet=alphabet)


class TimestampMixin:
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)
    deleted_at = fields.DatetimeField(null=True)


class GuidMixin(models.Model):
    id = NANOIDField(primary_key=True)

    class Meta:
        abstract = True
