from contextvars import ContextVar, Token

_PAT_ID: ContextVar[str | None] = ContextVar('pat_id', default=None)


def set_pat_id(pat_id: str | None) -> Token[str | None]:
    return _PAT_ID.set(pat_id)


def reset_pat_id(token: Token[str | None]) -> None:
    _PAT_ID.reset(token)


def get_pat_id() -> str | None:
    return _PAT_ID.get()
