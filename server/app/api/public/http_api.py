from fastapi import APIRouter, Header, Request
from starlette.responses import Response

from app.api import PublicRouter
from app.core import context
from app.core.response import ErrorResponse
from app.model.transport import Transport
from app.services.public import PublicGatewayAccessManager

router = APIRouter(route_class=PublicRouter, tags=['public-http-api'])


def _request_host(request: Request) -> str | None:
    return request.headers.get('host') or request.url.hostname


@router.api_route(
    '/{full_path:path}',
    methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'],
    include_in_schema=False,
)
async def call_http_api(
    full_path: str,
    request: Request,
    authorization: str | None = Header(default=None, alias='Authorization'),
) -> Response:
    host = _request_host(request)
    if PublicGatewayAccessManager.match_host(host, Transport.HTTP_API) is None:
        return ErrorResponse(status_code=404, msg='Not Found')
    manager = request.app.state.public_http_api_manager
    result = await manager.call(
        host=host,
        method=request.method,
        raw_path=full_path,
        headers=[(name.decode('latin-1'), value.decode('latin-1')) for name, value in request.headers.raw],
        query=list(request.query_params.multi_items()),
        body=await request.body(),
        authorization=authorization,
        client_ip=context.client_ip(request) or 'unknown',
    )
    if not result.protocol_matched:
        return ErrorResponse(status_code=404, msg='Not Found')
    response = Response(content=result.body, status_code=result.status_code)
    response.raw_headers = [(name.encode('latin-1'), value.encode('latin-1')) for name, value in result.headers]
    return response
