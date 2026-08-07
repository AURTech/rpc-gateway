from starlette.requests import Request

from app.core.errors import ForbiddenError
from app.core.origin import normalize_origin
from app.services.auth.settings import get_auth_settings

CSRF_HEADER_NAME = 'X-RPC-Gateway-CSRF'
CSRF_HEADER_VALUE = '1'
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def validate_csrf_request(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER_NAME) != CSRF_HEADER_VALUE:
        raise ForbiddenError('CSRF validation failed.')

    origin_value = request.headers.get('origin')
    if origin_value is None:
        return
    try:
        origin = normalize_origin(origin_value)
    except ValueError as exc:
        raise ForbiddenError('CSRF validation failed.') from exc
    if origin not in get_auth_settings().allowed_frontend_origins:
        raise ForbiddenError('CSRF validation failed.')
