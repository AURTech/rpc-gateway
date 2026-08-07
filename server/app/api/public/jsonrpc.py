import json
from collections.abc import AsyncIterator

import orjson
from fastapi import APIRouter, Header, Request
from starlette.responses import Response, StreamingResponse

from app.api import PublicRouter
from app.api.deps import PublicJsonRpcManagerDep
from app.core import context
from app.core.response import ErrorResponse, JsonFallbackResponse

router = APIRouter(
    default_response_class=JsonFallbackResponse,
    route_class=PublicRouter,
    tags=['public-jsonrpc'],
)


def _request_host(request: Request) -> str | None:
    return request.headers.get('host') or request.url.hostname


async def _stream_raw_result(request_id: str | int | None, raw_result: bytes) -> AsyncIterator[bytes]:
    yield b'{"jsonrpc":"2.0","id":'
    try:
        yield orjson.dumps(request_id)
    except TypeError:
        yield json.dumps(request_id, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    yield b',"result":'
    yield raw_result
    yield b'}'


async def _call_jsonrpc(
    request: Request,
    manager: PublicJsonRpcManagerDep,
    path_key: str | None,
    authorization: str | None,
) -> Response:
    result = await manager.call(
        host=_request_host(request),
        body=await request.body(),
        path_key=path_key,
        authorization=authorization,
        client_ip=context.client_ip(request) or 'unknown',
    )
    if result.raw_result is not None:
        return StreamingResponse(
            _stream_raw_result(result.request_id, result.raw_result),
            status_code=result.status_code,
            media_type='application/json',
            headers=result.headers,
        )
    if result.response is None:
        if result.status_code == 404:
            return ErrorResponse(status_code=404, msg='Not Found', headers=result.headers)
        return Response(status_code=result.status_code, headers=result.headers)
    content = result.response.model_dump(mode='json', exclude_unset=True)
    return JsonFallbackResponse(content, status_code=result.status_code, headers=result.headers)


@router.post('/', include_in_schema=False)
async def call_jsonrpc_with_header(
    request: Request,
    manager: PublicJsonRpcManagerDep,
    authorization: str | None = Header(default=None, alias='Authorization'),
) -> Response:
    return await _call_jsonrpc(request, manager, None, authorization)


@router.post('/{path_key}', include_in_schema=False)
async def call_jsonrpc_with_path(
    request: Request,
    manager: PublicJsonRpcManagerDep,
    path_key: str,
    authorization: str | None = Header(default=None, alias='Authorization'),
) -> Response:
    return await _call_jsonrpc(request, manager, path_key, authorization)
