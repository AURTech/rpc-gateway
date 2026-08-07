import contextlib
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.api.idempotency import (
    IdempotencyExecution,
    IdempotencyReplay,
    begin_idempotent_request,
    replay_response,
    save_idempotent_response,
)
from app.core.response import wr_o_resp


class BaseRouter(APIRouter):
    def add_api_route(
        self,
        path: str,
        endpoint: Any,
        *,
        response_model: type[BaseModel] | None = None,
        responses: dict[int | str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        status_code = kwargs.get('status_code') or 200
        default = wr_o_resp(response_model, status_code)
        if responses:
            responses = responses.copy()
            if status_code != 200:
                responses.pop(200, None)
            default.update(responses)
        responses = default
        return super().add_api_route(path, endpoint, response_model=response_model, responses=responses, **kwargs)


class DashRouter(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        route_handler = super().get_route_handler()

        async def idempotent_route_handler(request: Request) -> Response:
            state = await begin_idempotent_request(request)
            if isinstance(state, IdempotencyReplay):
                return replay_response(state)
            try:
                response = await route_handler(request)
            except BaseException:
                if isinstance(state, IdempotencyExecution):
                    with contextlib.suppress(Exception):
                        await state.lease.release()
                raise
            if isinstance(state, IdempotencyExecution):
                await save_idempotent_response(state, response)
            return response

        return idempotent_route_handler


class PublicRouter(APIRoute):
    """Public protocol ingress route that bypasses the control-plane response envelope."""
