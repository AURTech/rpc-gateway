from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastlog import log
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import APIError
from app.core.response import ErrorResponse


def _trace_id(request: Request) -> str | None:
    value = getattr(request.state, 'trace_id', None)
    return value if isinstance(value, str) and value else None


def _format_validation_errors(exc: RequestValidationError) -> str:
    """Parse validation errors into a user-friendly message."""
    errors = exc.errors()
    messages: list[str] = []
    for err in errors:
        loc = err.get('loc', ())
        # Skip 'body' prefix for request body validation
        path = '.'.join(str(x) for x in loc if x != 'body')
        msg = err.get('msg', 'Invalid value')
        messages.append(f'{path}: {msg}' if path else msg)
    user_message = '; '.join(messages) if messages else 'Validation failed'
    return user_message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> ErrorResponse:
        log.warning(f'APIError {exc.status_code}: {exc.msg}')
        return ErrorResponse(
            status_code=exc.status_code,
            msg=exc.msg,
            code=exc.code,
            details=exc.details,
            trace_id=_trace_id(request),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> ErrorResponse:
        message = _format_validation_errors(exc)
        log.warning(f'ValidationError: {message}')
        return ErrorResponse(status_code=422, msg=message, code='request.validation', trace_id=_trace_id(request))

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> ErrorResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            message = detail.get('msg') or detail.get('message') or str(detail)
        else:
            message = str(detail) if detail else 'error'
        log.warning(f'HTTPException {exc.status_code}: {message}')
        code = 'resource.not_found' if exc.status_code == 404 else 'request.http_error'
        return ErrorResponse(status_code=exc.status_code, msg=message, code=code, trace_id=_trace_id(request))

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> ErrorResponse:
        log.exception(f'Unhandled exception: {exc}')
        return ErrorResponse(
            status_code=500,
            msg='Internal server error.',
            code='internal.error',
            trace_id=_trace_id(request),
        )
