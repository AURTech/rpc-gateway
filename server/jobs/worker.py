import contextlib

from app import service_state
from app.core.config import CONF, validate_runtime_security
from app.infra import runtime
from app.infra.db import TORTOISE_ORM
from fastlog import configure, log
from taskiq import TaskiqEvents, TaskiqState
from tortoise import Tortoise

from jobs.registry import broker

validate_runtime_security(CONF)
configure(level=CONF.log_level, log_path=CONF.LOG_PATH)


def _clear_worker_runtime(state: TaskiqState) -> None:
    if 'runtime' in state:
        del state.runtime


def _clear_worker_stack(state: TaskiqState) -> None:
    if 'runtime_stack' in state:
        del state.runtime_stack


async def _close_worker_runtime(state: TaskiqState, *, http_bound: bool) -> None:
    runtime_stack = state.runtime_stack if 'runtime_stack' in state else None
    async with contextlib.AsyncExitStack() as stack:
        if runtime_stack is not None:
            stack.callback(_clear_worker_stack, state)
            stack.push_async_callback(runtime_stack.aclose)
        stack.callback(_clear_worker_runtime, state)
        stack.push_async_callback(
            service_state.close_runtime_state,
            http_bound=http_bound,
        )


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _worker_startup(state: TaskiqState) -> None:
    runtime_stack = contextlib.AsyncExitStack()
    http_bound = False
    orm_started = False
    try:
        clients = await runtime_stack.enter_async_context(runtime.open_runtime_clients())
        state.runtime_stack = runtime_stack
        state.runtime = clients
        service_state.bind_redis(clients)
        service_state.bind_http_client(clients)
        http_bound = True
        await Tortoise.init(config=TORTOISE_ORM)
        orm_started = True
    except Exception:
        await _close_worker_runtime(state, http_bound=http_bound)
        if orm_started:
            await Tortoise.close_connections()
        raise
    log.info('TaskIQ worker ready')


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _worker_shutdown(state: TaskiqState) -> None:
    async with contextlib.AsyncExitStack() as stack:
        stack.push_async_callback(Tortoise.close_connections)
        stack.push_async_callback(_close_worker_runtime, state, http_bound=True)
    log.info('TaskIQ worker stopped')
