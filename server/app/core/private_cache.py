from starlette.datastructures import MutableHeaders

PRIVATE_CACHE_SCOPE_KEY = 'private_cache'

_PRIVATE_HEADERS = {
    'Cache-Control': 'private, no-store',
    'Pragma': 'no-cache',
    'Expires': '0',
}


def apply_private_cache(headers: MutableHeaders) -> None:
    for name, value in _PRIVATE_HEADERS.items():
        headers[name] = value
