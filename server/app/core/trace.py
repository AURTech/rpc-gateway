import re
from collections.abc import Iterator
from contextlib import contextmanager

from fastlog import log
from loguru._logger import context as loguru_context
from nanoid import generate

TRACE_ID_HEADER = 'A-Trace-ID'
TASK_TRACE_LABEL = '_aio_trace_id'
TRACE_ID_SIZE = 18
TRACE_ID_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
TRACE_ID_PATTERN = re.compile(rf'^[{TRACE_ID_ALPHABET}]{{1,64}}$')


def generate_trace_id() -> str:
    return generate(alphabet=TRACE_ID_ALPHABET, size=TRACE_ID_SIZE)


def normalize_trace_id(value: str | None = None) -> str:
    if value is None:
        return generate_trace_id()
    trace_id = value.strip()
    if TRACE_ID_PATTERN.fullmatch(trace_id):
        return trace_id
    return generate_trace_id()


def get_current_trace_id() -> str:
    context = loguru_context.get()
    trace_id = context.get('trace_id')
    sub_trace_id = context.get('sub_trace_id')

    if trace_id and sub_trace_id:
        return f'{trace_id}:{sub_trace_id}'
    return trace_id or sub_trace_id or ''


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    current_trace_id = trace_id.strip() if trace_id else generate_trace_id()
    with log.contextualize(trace_id=current_trace_id):
        yield current_trace_id
