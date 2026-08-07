from typing import NoReturn

from app.core.errors import RateLimitError


def default_callback(*args: object, **kwargs: object) -> NoReturn:
    raise RateLimitError()
