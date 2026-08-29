from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from tortoise.contrib.fastapi import RegisterTortoise

from app import service_state
from app.core.config import CONF
from app.infra import runtime
from app.infra.broker import broker
from app.infra.db import TORTOISE_ORM


async def _close_lifespan_runtime(*, broker_started: bool) -> None:
    async with AsyncExitStack() as stack:
        stack.push_async_callback(
            service_state.close_runtime_state,
            http_bound=False,
        )
        if broker_started:
            stack.push_async_callback(broker.shutdown)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run the API process lifecycle for control-plane services."""
    async with runtime.open_runtime_clients() as clients:
        broker_started = False
        try:
            app.state.redis = clients.redis
            app.state.shared_http_client = clients.shared_http_client
            service_state.bind_redis(clients)
            service_state.init_managers(app, clients.shared_http_client, clients.redis)
            health_dispatcher = app.state.health_dispatcher
            circuit_manager = app.state.circuit_manager
            tip_dispatcher = app.state.tip_dispatcher
            system_cache_manager = app.state.system_cache_manager
            usage_recorder = app.state.usage_recorder
            await broker.startup()
            broker_started = True
            async with RegisterTortoise(app, config=TORTOISE_ORM, generate_schemas=False):
                jsonrpc_rate_limit_policy_manager = app.state.jsonrpc_rate_limit_policy_manager
                jsonrpc_admission_manager = app.state.jsonrpc_admission_manager
                http_api_rate_limit_policy_manager = app.state.http_api_rate_limit_policy_manager
                http_api_admission_manager = app.state.http_api_admission_manager
                try:
                    await jsonrpc_rate_limit_policy_manager.start()
                    await jsonrpc_admission_manager.start()
                    await http_api_rate_limit_policy_manager.start()
                    await http_api_admission_manager.start()
                    await health_dispatcher.start()
                    await circuit_manager.start()
                    await tip_dispatcher.start()
                    await usage_recorder.start()
                    yield
                finally:
                    await usage_recorder.close(drain_seconds=5)
                    if system_cache_manager is not None:
                        await system_cache_manager.close(drain_seconds=5)
                    await tip_dispatcher.close(drain_seconds=CONF.RUNTIME_TIP_DISPATCHER_SHUTDOWN_DRAIN_SECONDS)
                    await circuit_manager.close(drain_seconds=CONF.RUNTIME_HEALTH_DISPATCHER_SHUTDOWN_DRAIN_SECONDS)
                    await health_dispatcher.close(drain_seconds=CONF.RUNTIME_HEALTH_DISPATCHER_SHUTDOWN_DRAIN_SECONDS)
                    await http_api_admission_manager.close(
                        drain_seconds=CONF.PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_SHUTDOWN_DRAIN_SECONDS,
                    )
                    await http_api_rate_limit_policy_manager.close()
                    await jsonrpc_admission_manager.close(
                        drain_seconds=CONF.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_SHUTDOWN_DRAIN_SECONDS,
                    )
                    await jsonrpc_rate_limit_policy_manager.close()
        finally:
            await _close_lifespan_runtime(broker_started=broker_started)
