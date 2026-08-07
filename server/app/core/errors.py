class APIError(Exception):
    status_code: int = 500
    msg: str = 'Internal server error.'
    code: str = 'internal.error'

    def __init__(
        self,
        msg: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.msg = msg or self.__class__.msg
        self.code = code or self.__class__.code
        self.details = details
        super().__init__(self.msg)


class BadRequestError(APIError):
    status_code = 400
    msg = 'Bad request.'
    code = 'request.invalid'


class ConflictError(APIError):
    status_code = 409
    msg = 'Request conflicts with existing state.'
    code = 'resource.conflict'


class AuthenticationError(APIError):
    status_code = 401
    msg = 'Authentication required.'
    code = 'auth.required'


class ForbiddenError(APIError):
    status_code = 403
    msg = 'Permission denied.'
    code = 'auth.forbidden'


class NotfoundError(APIError):
    status_code = 404
    msg = 'Resource not found.'
    code = 'resource.not_found'


class RateLimitError(APIError):
    status_code = 429
    msg = 'Request too fast, please try again later.'
    code = 'rate_limited'


class InternalError(APIError):
    status_code = 500
    msg = 'System error. Please contact administrator or try again later.'
    code = 'internal.error'


class UnavailableError(APIError):
    status_code = 503
    msg = 'Service is unavailable.'
    code = 'service.unavailable'
