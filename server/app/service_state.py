import contextlib

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from app.clients.endpoint import EndpointHttpClient
from app.clients.transport import HttpTransport
from app.core.config import CONF
from app.infra import runtime
from app.infra.db import SYSTEM_CACHE_COORDINATION_DB_CONNECTION, SYSTEM_CACHE_RETENTION_DB_CONNECTION
from app.infra.http_client import SharedHttpClient
from app.infra.outbound_policy import build_outbound_target_policy
from app.model.runtime_state.circuit import CircuitPolicy
from app.services.auth import AuthManager
from app.services.auth.password import PasswordWorker
from app.services.base import Manager
from app.services.endpoint import EndpointAccessManager, EndpointHealthManager, EndpointManager, ManagedEndpointManager
from app.services.endpoint.probe import EndpointProbeManager
from app.services.http_api_forwarding import HttpApiForwardingManager
from app.services.http_api_rate_limit import HttpApiAdmissionManager, HttpApiRateLimitPolicyManager
from app.services.http_api_route import DatabaseEndpointRouteReferenceLookup, DatabaseHttpApiRoutePlanProvider
from app.services.jsonrpc_forwarding import JsonRpcForwardingManager
from app.services.jsonrpc_rate_limit import JsonRpcAdmissionManager
from app.services.jsonrpc_rate_limit.policy import JsonRpcRateLimitPolicyManager
from app.services.jsonrpc_route import DatabaseJsonRpcRoutePlanProvider
from app.services.provider import ProviderManager
from app.services.public import (
    DatabasePublicGatewayLookup,
    DatabasePublicIdentityLookup,
    PublicGatewayAccessManager,
    PublicHttpApiManager,
    PublicJsonRpcManager,
)
from app.services.runtime_state.circuit import CircuitManager
from app.services.runtime_state.endpoint.health import HealthDispatcher, HealthManager
from app.services.runtime_state.endpoint.tip import TipDispatcher, TipManager
from app.services.runtime_state.endpoint.tip.store import TipStore
from app.services.system_cache import SystemCacheManager
from app.services.system_cache.flight import PostgresRetentionFlight, RedisTtlFlight
from app.services.system_cache.limits import FLIGHT_LEASE_MS, REDIS_IO_TIMEOUT_SECONDS, flight_wait_seconds
from app.services.system_cache.store import HybridSystemCacheStore, PostgresRetentionStore, RedisTtlStore
from app.services.system_http_api_cache import SystemHttpApiCacheManager
from app.services.system_http_api_cache.policy import SystemHttpApiCachePolicy
from app.services.system_jsonrpc_cache import SystemJsonRpcCacheManager
from app.services.system_jsonrpc_cache.policy import SystemJsonRpcCachePolicy
from app.services.usage import GatewayUsageRecorder


def bind_redis(clients: runtime.RuntimeClients) -> None:
    Manager.set_redis(clients.redis)


def bind_http_client(clients: runtime.RuntimeClients) -> None:
    SharedHttpClient.set_client(clients.shared_http_client)


def init_managers(app: FastAPI, shared_http_client: httpx.AsyncClient, redis_client: Redis) -> None:
    password_worker = PasswordWorker(max_concurrency=CONF.AUTH_PASSWORD_MAX_CONCURRENCY)
    transport = HttpTransport(shared_http_client)
    target_policy = build_outbound_target_policy()
    endpoint_client = EndpointHttpClient(transport)
    route_references = DatabaseEndpointRouteReferenceLookup()
    health_manager = HealthManager(redis_client)
    health_dispatcher = HealthDispatcher(
        max_batches=CONF.RUNTIME_HEALTH_DISPATCHER_MAX_BATCHES,
        max_waiters=CONF.RUNTIME_HEALTH_DISPATCHER_MAX_WAITERS,
        max_waiters_per_batch=CONF.RUNTIME_HEALTH_DISPATCHER_MAX_WAITERS_PER_BATCH,
        record_timeout_ms=CONF.RUNTIME_HEALTH_DISPATCHER_RECORD_TIMEOUT_MS,
        coalesce_ms=CONF.RUNTIME_HEALTH_DISPATCHER_COALESCE_MS,
        writer=health_manager.record_batch,
    )
    tip_manager = TipManager(TipStore(redis_client))
    tip_dispatcher = TipDispatcher(
        max_items=CONF.RUNTIME_TIP_DISPATCHER_MAX_ITEMS,
        writer=tip_manager.record,
    )
    probe_manager = EndpointProbeManager(
        http_client=endpoint_client,
        target_policy=target_policy,
        timeout_seconds=CONF.ENDPOINT_HEALTH_CHECK_TIMEOUT_SECONDS,
        max_response_bytes=CONF.ENDPOINT_HEALTH_CHECK_MAX_RESPONSE_BYTES,
    )
    app.state.auth_manager = AuthManager(http_client=shared_http_client, password_worker=password_worker)
    endpoint_access_manager = EndpointAccessManager(endpoint_client, target_policy)
    circuit_manager = CircuitManager(
        redis_client,
        CircuitPolicy(
            failure_threshold=CONF.RUNTIME_CIRCUIT_HARD_FAILURE_THRESHOLD,
            window_seconds=CONF.RUNTIME_CIRCUIT_WINDOW_SECONDS,
            window_bucket_seconds=CONF.RUNTIME_CIRCUIT_WINDOW_BUCKET_SECONDS,
            window_min_samples=CONF.RUNTIME_CIRCUIT_MIN_SAMPLES,
            window_failure_rate=CONF.RUNTIME_CIRCUIT_FAILURE_RATE,
            open_seconds=CONF.RUNTIME_CIRCUIT_OPEN_SECONDS,
            max_open_seconds=CONF.RUNTIME_CIRCUIT_MAX_OPEN_SECONDS,
            recovery_successes=CONF.RUNTIME_CIRCUIT_RECOVERY_SUCCESSES,
            probe_seconds=CONF.RUNTIME_CIRCUIT_PROBE_SECONDS,
            throttle_seconds=CONF.RUNTIME_CIRCUIT_THROTTLE_SECONDS,
            throttle_max_seconds=CONF.RUNTIME_CIRCUIT_THROTTLE_MAX_SECONDS,
        ),
    )
    jsonrpc_rate_limit_policy_manager = JsonRpcRateLimitPolicyManager(
        refresh_seconds=CONF.PUBLIC_JSONRPC_RATE_LIMIT_POLICY_REFRESH_SECONDS
    )
    jsonrpc_admission_manager = JsonRpcAdmissionManager(
        redis_client,
        jsonrpc_rate_limit_policy_manager,
        backend=CONF.PUBLIC_JSONRPC_RATE_LIMIT_BACKEND,
        workers=CONF.WORKERS,
        expected_replicas=CONF.PUBLIC_JSONRPC_RATE_LIMIT_EXPECTED_REPLICAS,
        shadow_max_pending=CONF.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_MAX_PENDING,
        shadow_workers=CONF.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_WORKERS,
        shadow_redis_timeout_ms=CONF.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_REDIS_TIMEOUT_MS,
    )
    jsonrpc_route_plans = DatabaseJsonRpcRoutePlanProvider()
    jsonrpc_forwarding_manager = JsonRpcForwardingManager(
        endpoint_access_manager,
        jsonrpc_route_plans,
        circuit_manager,
        health_dispatcher,
        max_attempts=CONF.JSONRPC_FORWARDING_MAX_ATTEMPTS,
        trace_method_prefixes=tuple(CONF.RUNTIME_CIRCUIT_TRACE_METHOD_PREFIXES),
    )
    admin_jsonrpc_forwarding_manager = JsonRpcForwardingManager(
        endpoint_access_manager,
        jsonrpc_route_plans,
        circuit_manager,
        health_dispatcher,
        max_attempts=CONF.JSONRPC_FORWARDING_MAX_ATTEMPTS,
        trace_method_prefixes=tuple(CONF.RUNTIME_CIRCUIT_TRACE_METHOD_PREFIXES),
        tip=tip_dispatcher,
    )
    http_api_rate_limit_policy_manager = HttpApiRateLimitPolicyManager(
        refresh_seconds=CONF.PUBLIC_HTTP_API_RATE_LIMIT_POLICY_REFRESH_SECONDS
    )
    http_api_admission_manager = HttpApiAdmissionManager(
        redis_client,
        http_api_rate_limit_policy_manager,
        backend=CONF.PUBLIC_HTTP_API_RATE_LIMIT_BACKEND,
        workers=CONF.WORKERS,
        expected_replicas=CONF.PUBLIC_HTTP_API_RATE_LIMIT_EXPECTED_REPLICAS,
        shadow_max_pending=CONF.PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_MAX_PENDING,
        shadow_workers=CONF.PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_WORKERS,
        shadow_redis_timeout_ms=CONF.PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_REDIS_TIMEOUT_MS,
    )
    http_api_forwarding_manager = HttpApiForwardingManager(
        endpoint_access_manager,
        DatabaseHttpApiRoutePlanProvider(),
        circuit_manager,
        health_dispatcher,
        max_attempts=CONF.HTTP_API_FORWARDING_MAX_ATTEMPTS,
    )
    system_cache_manager: SystemCacheManager | None = None
    system_jsonrpc_cache_manager: SystemJsonRpcCacheManager | None = None
    system_http_api_cache_manager: SystemHttpApiCacheManager | None = None
    if CONF.SYSTEM_CACHE_ENABLED:
        system_cache_manager = SystemCacheManager(
            HybridSystemCacheStore(
                RedisTtlStore(redis_client),
                PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION),
            ),
            RedisTtlFlight(
                redis_client,
                lease_ms=FLIGHT_LEASE_MS,
                io_timeout_seconds=REDIS_IO_TIMEOUT_SECONDS,
            ),
            postgres_flight=PostgresRetentionFlight(
                lease_ms=FLIGHT_LEASE_MS,
                io_timeout_seconds=REDIS_IO_TIMEOUT_SECONDS,
                connection_name=SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
            ),
            flight_wait_seconds=flight_wait_seconds(
                max(CONF.JSONRPC_FORWARDING_MAX_ATTEMPTS, CONF.HTTP_API_FORWARDING_MAX_ATTEMPTS)
            ),
        )
        system_jsonrpc_cache_manager = SystemJsonRpcCacheManager(
            system_cache_manager,
            SystemJsonRpcCachePolicy(
                redis_ttl_ms=CONF.SYSTEM_CACHE_REDIS_TTL_MS,
                postgres_retention_seconds=CONF.SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN,
            ),
        )
        system_http_api_cache_manager = SystemHttpApiCacheManager(
            system_cache_manager,
            SystemHttpApiCachePolicy(
                redis_ttl_ms=CONF.SYSTEM_CACHE_REDIS_TTL_MS,
                postgres_retention_seconds=CONF.SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN,
            ),
        )
    app.state.system_cache_manager = system_cache_manager
    app.state.endpoint_access_manager = endpoint_access_manager
    app.state.endpoint_manager = EndpointManager(route_references)
    app.state.jsonrpc_rate_limit_policy_manager = jsonrpc_rate_limit_policy_manager
    app.state.jsonrpc_admission_manager = jsonrpc_admission_manager
    app.state.http_api_rate_limit_policy_manager = http_api_rate_limit_policy_manager
    app.state.http_api_admission_manager = http_api_admission_manager
    public_access_manager = PublicGatewayAccessManager(
        DatabasePublicIdentityLookup(),
        DatabasePublicGatewayLookup(),
    )
    usage_recorder = GatewayUsageRecorder()
    app.state.usage_recorder = usage_recorder
    app.state.public_jsonrpc_manager = PublicJsonRpcManager(
        public_access_manager,
        jsonrpc_admission_manager,
        jsonrpc_forwarding_manager,
        system_jsonrpc_cache_manager,
        admin_forwarding=admin_jsonrpc_forwarding_manager,
        usage=usage_recorder,
    )
    app.state.public_http_api_manager = PublicHttpApiManager(
        public_access_manager,
        http_api_admission_manager,
        http_api_forwarding_manager,
        usage_recorder,
        system_cache=system_http_api_cache_manager,
    )
    app.state.endpoint_health_manager = EndpointHealthManager(
        probe_manager=probe_manager,
        health_manager=health_manager,
    )
    app.state.health_dispatcher = health_dispatcher
    app.state.circuit_manager = circuit_manager
    app.state.tip_dispatcher = tip_dispatcher
    app.state.provider_manager = ProviderManager(transport, ManagedEndpointManager(route_references))


async def close_runtime_state(*, http_bound: bool) -> None:
    """Clear process-level runtime bindings and cache state."""
    async with contextlib.AsyncExitStack() as stack:
        stack.callback(Manager.clear_redis)
        if http_bound:
            stack.callback(SharedHttpClient.clear)
