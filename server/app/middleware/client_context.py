from app.core import context
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send


class ClientContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        state = scope.setdefault('state', {})
        state['connect_ip'] = context.client_ip(connection)
        state['country'] = context.country(connection)
        await self._app(scope, receive, send)
