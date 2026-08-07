import asyncio
from collections.abc import Callable
from contextlib import suppress

import anyio
from app.core.response import ErrorResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

INVALID_CONTENT_LENGTH_MESSAGE = 'Content-Length header is invalid.'
REQUEST_BODY_READ_TIMEOUT_MESSAGE = 'Request body read timed out.'
REQUEST_BODY_TOO_LARGE_MESSAGE = 'Request body exceeds the configured limit.'


def _content_length(scope: Scope) -> int | None:
    raw_values = [value for name, value in scope.get('headers', []) if name.lower() == b'content-length']
    if not raw_values:
        return None
    values: list[int] = []
    for raw_value in raw_values:
        parts = raw_value.split(b',')
        if not parts:
            raise ValueError(INVALID_CONTENT_LENGTH_MESSAGE)
        for raw_part in parts:
            part = raw_part.strip()
            if not part or not part.isdigit():
                raise ValueError(INVALID_CONTENT_LENGTH_MESSAGE)
            values.append(int(part))
    if not values or any(value != values[0] for value in values[1:]):
        raise ValueError(INVALID_CONTENT_LENGTH_MESSAGE)
    return values[0]


class RequestBodyLimitMiddleware:
    """Buffer a bounded request body before entering HTTP handlers.

    One absolute deadline covers the complete body rather than restarting for
    each chunk. The limit applies to every HTTP method because GET and HEAD can
    still carry payload frames without declaring Content-Length.

    After buffering, this middleware owns the upstream receive callable and replays one complete
    request frame downstream. A disconnect before the final response cancels the application task
    and waits for cleanup; after a completed response, receive events continue to flow without
    cancelling response background work.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        read_timeout_seconds: int = 15,
        error_response_factory: Callable[[Scope, int, str], Response] | None = None,
    ) -> None:
        self._app = app
        self._max_bytes = max_bytes
        self._read_timeout_seconds = read_timeout_seconds
        self._error_response_factory = error_response_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return

        try:
            content_length = _content_length(scope)
        except ValueError:
            await self._send_error(scope, receive, send, status_code=400, message=INVALID_CONTENT_LENGTH_MESSAGE)
            return
        if content_length is not None and content_length > self._max_bytes:
            await self._send_error(scope, receive, send, status_code=413, message=REQUEST_BODY_TOO_LARGE_MESSAGE)
            return
        body = bytearray()
        body_too_large = False
        try:
            with anyio.fail_after(self._read_timeout_seconds):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    if len(body) + len(chunk) > self._max_bytes:
                        body_too_large = True
                        break
                    body.extend(chunk)
                    if not message.get('more_body', False):
                        break
        except TimeoutError:
            await self._send_error(scope, receive, send, status_code=408, message=REQUEST_BODY_READ_TIMEOUT_MESSAGE)
            return
        if body_too_large:
            await self._send_error(scope, receive, send, status_code=413, message=REQUEST_BODY_TOO_LARGE_MESSAGE)
            return

        replayed = False
        pending_messages: asyncio.Queue[Message] = asyncio.Queue(maxsize=1)
        response_complete = False
        disconnected = False
        disconnect_cancel_requested = False

        async def replay_body() -> Message:
            nonlocal replayed
            if replayed:
                return await pending_messages.get()
            replayed = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

        async def send_response(message: Message) -> None:
            nonlocal response_complete
            await send(message)
            if message['type'] == 'http.response.pathsend' or (
                message['type'] == 'http.response.body' and not message.get('more_body', False)
            ):
                response_complete = True

        async def listen_for_disconnect() -> None:
            nonlocal disconnect_cancel_requested, disconnected
            while True:
                message = await receive()
                await pending_messages.put(message)
                if message['type'] != 'http.disconnect':
                    continue
                disconnected = True
                if not response_complete and application_task.cancelling() == 0:
                    disconnect_cancel_requested = application_task.cancel()
                return

        async def run_application() -> None:
            await self._app(scope, replay_body, send_response)

        application_task = asyncio.create_task(run_application())
        disconnect_task = asyncio.create_task(listen_for_disconnect())
        try:
            completed, _ = await asyncio.wait(
                (application_task, disconnect_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if application_task in completed:
                disconnect_task.cancel()
                with suppress(asyncio.CancelledError):
                    await disconnect_task
                try:
                    await application_task
                except asyncio.CancelledError:
                    if disconnect_cancel_requested and disconnected:
                        return
                    raise
                return

            await disconnect_task
            try:
                await application_task
            except asyncio.CancelledError:
                if disconnect_cancel_requested and disconnected:
                    return
                raise
        finally:
            for task in (application_task, disconnect_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(application_task, disconnect_task, return_exceptions=True)

    async def _send_error(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        message: str,
    ) -> None:
        if self._error_response_factory is None:
            response = ErrorResponse(status_code=status_code, msg=message)
        else:
            response = self._error_response_factory(scope, status_code, message)
        await response(scope, receive, send)
