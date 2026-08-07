import time

from app.core.trace import TRACE_ID_HEADER, normalize_trace_id
from app.services.gateway.host import is_gateway_host
from fastlog import log
from starlette.datastructures import MutableHeaders
from starlette.requests import ClientDisconnect, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _route_template(request: Request) -> str | None:
    route = request.scope.get('route')
    path = getattr(route, 'path', None)
    return path if isinstance(path, str) else None


def _request_path(request: Request) -> str:
    template = _route_template(request)
    if template is not None:
        return template
    path = request.url.path or '-'
    host = request.headers.get('host') or request.url.hostname
    if not is_gateway_host(host):
        return path
    return _redact_api_key(path)


def _redact_api_key(path: str) -> str:
    segments = path.split('/')
    if len(segments) < 2 or not segments[1]:
        return path
    segments[1] = '{api_key}'
    return '/'.join(segments)


class RequestLogMiddleware:
    """Log one HTTP lifecycle without introducing an ASGI task boundary.

    Only explicit receive disconnects, Starlette ClientDisconnect exceptions, and OSError raised by
    the server send callable are classified as client disconnects. Application failures always
    propagate and take precedence over a concurrently observed disconnect.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        start_time = time.perf_counter()
        status_code = 500
        response_started = False
        response_complete = False
        disconnected = False
        application_failed = False
        trace_id = normalize_trace_id(request.headers.get(TRACE_ID_HEADER))
        state = scope.setdefault('state', {})
        state['trace_id'] = trace_id

        async def receive_with_disconnect() -> Message:
            nonlocal disconnected
            message = await receive()
            if message['type'] == 'http.disconnect':
                disconnected = True
            return message

        async def send_with_trace(message: Message) -> None:
            nonlocal disconnected, response_complete, response_started, status_code
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers[TRACE_ID_HEADER] = trace_id
            try:
                await send(message)
            except OSError as exc:
                disconnected = True
                raise ClientDisconnect() from exc
            if message['type'] == 'http.response.start':
                response_started = True
                status_code = message['status']
            elif message['type'] == 'http.response.pathsend' or (
                message['type'] == 'http.response.body' and not message.get('more_body', False)
            ):
                response_complete = True

        with log.contextualize(trace_id=trace_id):
            try:
                await self._app(scope, receive_with_disconnect, send_with_trace)
            except ClientDisconnect:
                disconnected = True
            except BaseException:
                application_failed = True
                status_code = 500
                raise
            else:
                if not response_started and not disconnected:
                    raise RuntimeError('HTTP application returned without starting a response.')
                if response_started and not response_complete and not disconnected:
                    raise RuntimeError('HTTP application returned before completing the response.')
            finally:
                process_time = round((time.perf_counter() - start_time) * 1000, 2)
                request_path = _request_path(request)
                connect_ip = state.get('connect_ip') or '-'
                country = state.get('country') or '-'
                pat_id = state.get('pat_id')
                auth_suffix = f' PAT:{pat_id}' if isinstance(pat_id, str) and pat_id else ''
                if disconnected and not response_complete and not application_failed:
                    log_message = (
                        f'{request.method} {request_path} disconnected {process_time}ms {connect_ip} {country}{auth_suffix}'
                    )
                    log.bind(action='http').info(log_message)
                else:
                    log_message = (
                        f'{request.method} {request_path} {status_code} {process_time}ms {connect_ip} {country}{auth_suffix}'
                    )
                    if status_code == 403 or status_code >= 500:
                        log.bind(action='http').error(log_message)
                    else:
                        log.bind(action='http').info(log_message)
