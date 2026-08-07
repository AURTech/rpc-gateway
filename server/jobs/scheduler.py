import contextlib

from app import service_state
from app.core.config import CONF, validate_runtime_security
from app.infra import runtime
from app.infra.db import TORTOISE_ORM
from fastlog import log
from taskiq import AsyncBroker, TaskiqScheduler
from taskiq.abc.schedule_source import ScheduleSource
from taskiq.schedule_sources.label_based import LabelScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask
from tortoise import Tortoise

from jobs.provider import PROVIDER_RECONCILE_SCHEDULE, ProviderScheduleSource, reconcile_due_providers
from jobs.registry import broker


class GatewayScheduler(TaskiqScheduler):
    def __init__(self, broker: AsyncBroker, sources: list[ScheduleSource]) -> None:
        super().__init__(broker, sources)
        self._runtime_stack: contextlib.AsyncExitStack | None = None
        self._http_bound = False
        self._orm_started = False

    async def startup(self) -> None:
        await super().startup()
        runtime_stack = contextlib.AsyncExitStack()
        try:
            clients = await runtime_stack.enter_async_context(runtime.open_runtime_clients())
            service_state.bind_redis(clients)
            service_state.bind_http_client(clients)
            self._http_bound = True
            await Tortoise.init(config=TORTOISE_ORM)
            self._orm_started = True
        except Exception:
            await service_state.close_runtime_state(cache_started=False, http_bound=self._http_bound)
            await runtime_stack.aclose()
            await super().shutdown()
            raise
        self._runtime_stack = runtime_stack
        log.info('TaskIQ scheduler ready')

    async def on_ready(self, source: ScheduleSource, task: ScheduledTask) -> None:
        if task.task_name == PROVIDER_RECONCILE_SCHEDULE:
            await reconcile_due_providers()
            return
        await super().on_ready(source, task)

    async def shutdown(self) -> None:
        async with contextlib.AsyncExitStack() as stack:
            stack.push_async_callback(super().shutdown)
            if self._runtime_stack is not None:
                stack.push_async_callback(self._runtime_stack.aclose)
            stack.push_async_callback(
                service_state.close_runtime_state,
                cache_started=False,
                http_bound=self._http_bound,
            )
            if self._orm_started:
                stack.push_async_callback(Tortoise.close_connections)
        log.info('TaskIQ scheduler stopped')


validate_runtime_security(CONF)
scheduler = GatewayScheduler(broker, sources=[LabelScheduleSource(broker), ProviderScheduleSource()])
