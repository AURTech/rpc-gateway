from typing import Final

KEY_GLOB_CHARS: Final[frozenset[str]] = frozenset({'*', '?', '[', ']'})


def validate_key_part(part: str) -> str:
    if not part or ':' in part or KEY_GLOB_CHARS & set(part):
        raise ValueError('Invalid Redis key part.')
    return part


def _pattern_part(part: str) -> str:
    if not part or ':' in part:
        raise ValueError('Invalid Redis pattern part.')
    return part


def join_key(namespace: str, *parts: str) -> str:
    key_parts = [validate_key_part(part) for part in (namespace, *parts)]
    return ':'.join(key_parts)


def join_pattern(namespace: str, *parts: str) -> str:
    pattern_parts = [_pattern_part(part) for part in (namespace, *parts)]
    return ':'.join(pattern_parts)


def join_prefix(namespace: str, *parts: str) -> str:
    return f'{join_key(namespace, *parts)}:'
