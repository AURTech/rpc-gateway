from typing import Any

from app.core.errors import RateLimitError
from app.core.response import ErrorResponse
from app.middleware.limiter.identifier import default_identifier
from pyrate_limiter import Limiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


async def _default_middleware_callback(request: Request) -> Response:
    return ErrorResponse(status_code=RateLimitError.status_code, msg=RateLimitError.msg)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limiter: Limiter,
        identifier=default_identifier,
        callback=_default_middleware_callback,
        blocking: bool = False,
        skip=None,
    ):
        super().__init__(app)
        self.limiter = limiter
        self.identifier = identifier
        self.callback = callback
        self.blocking = blocking
        self.skip = skip

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if self.skip and await self.skip(request):
            return await call_next(request)
        rate_key = await self.identifier(request)
        success = await self.limiter.try_acquire_async(rate_key, blocking=self.blocking)
        if not success:
            return await self.callback(request)

        return await call_next(request)
