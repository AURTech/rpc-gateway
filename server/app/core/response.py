from collections.abc import Mapping
from typing import Any, get_args

import orjson
from fastapi import BackgroundTasks
from pydantic import BaseModel, create_model
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse

from app.core.trace import get_current_trace_id


class UnifiedResponseModel(BaseModel):
    msg: str = 'ok'
    data: None | Any = None


class ErrorResponseModel(BaseModel):
    success: bool = False
    msg: str
    code: str = 'internal.error'
    details: dict[str, Any] | None = None
    trace_id: str | None = None


def wr_o_resp(model: type[BaseModel] | None, status_code: int = 200) -> dict[int | str, dict[str, Any]]:
    if model:
        model_names = [getattr(item, '__name__', 'Value') for item in get_args(model)]
        model_name = getattr(model, '__name__', 'Or'.join(model_names) or 'Data')
        wrapper_name = f'{model_name}Response'
        wrapped = create_model(wrapper_name, __base__=UnifiedResponseModel, data=(model, ...))
    else:
        wrapped = create_model('NoneResponse', __base__=UnifiedResponseModel, data=(None, None))
    return {status_code: {'model': wrapped}}


class OrjsonResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)


class JsonFallbackResponse(OrjsonResponse):
    def render(self, content: Any) -> bytes:
        try:
            return super().render(content)
        except TypeError:
            return JSONResponse.render(self, content)


class UnifiedResponse(OrjsonResponse):
    def __init__(
        self,
        data: Any,
        status_code: int = 200,
        msg: str = 'ok',
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTasks | None = None,
    ):
        _content = UnifiedResponseModel(msg=msg, data=data)
        super().__init__(
            _content.model_dump(),
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )


class ErrorResponse(OrjsonResponse):
    def __init__(
        self,
        status_code: int,
        msg: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
    ) -> None:
        error_code = code or {
            400: 'request.invalid',
            401: 'auth.required',
            403: 'auth.forbidden',
            404: 'resource.not_found',
            409: 'resource.conflict',
            422: 'request.validation',
            429: 'rate_limited',
            503: 'service.unavailable',
        }.get(status_code, 'internal.error')
        response_trace_id = trace_id or get_current_trace_id() or None
        _content = ErrorResponseModel(msg=msg, code=error_code, details=details, trace_id=response_trace_id)
        super().__init__(
            _content.model_dump(),
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )
