import re

HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
QUERY_PARAM_RE = re.compile(r'^[A-Za-z0-9_.~-]+$')
PATH_API_KEY_PLACEHOLDER = '{api_key}'
RESERVED_AUTH_HEADER_NAMES = frozenset(
    {
        'authorization',
        'connection',
        'content-length',
        'cookie',
        'forwarded',
        'host',
        'keep-alive',
        'set-cookie',
        'te',
        'trailer',
        'transfer-encoding',
        'upgrade',
    }
)
RESERVED_AUTH_HEADER_PREFIXES = ('access-control-', 'proxy-', 'x-forwarded-')


def validate_auth_header_name(value: str) -> str:
    name = value.strip()
    normalized = name.lower()
    if (
        not name
        or not HEADER_NAME_RE.fullmatch(name)
        or normalized in RESERVED_AUTH_HEADER_NAMES
        or normalized.startswith(RESERVED_AUTH_HEADER_PREFIXES)
    ):
        raise ValueError('HTTP auth header name is invalid.')
    return name


def validate_auth_query_param(value: str) -> str:
    name = value.strip()
    if not name or not QUERY_PARAM_RE.fullmatch(name):
        raise ValueError('HTTP auth query parameter is invalid.')
    return name
