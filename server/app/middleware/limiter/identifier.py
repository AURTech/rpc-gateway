from app.core import context
from starlette.requests import Request
from starlette.websockets import WebSocket


async def default_identifier(request: Request | WebSocket) -> str:
    ip = context.client_ip(request) or '127.0.0.1'
    return ip + ':' + request.scope['path']
