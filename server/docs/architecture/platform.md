# Platform and infrastructure

This document defines the FastAPI application lifecycle, shared layering, and infrastructure contracts. See the
[JSON-RPC](./jsonrpc-data-plane.md) and [HTTP API](./http-api-data-plane.md) documents for protocol data planes, and
[`README.md`](../../README.md) for the overview.

## Application factory and lifecycle

`app/__init__.py` creates the FastAPI application and validates production safety settings before startup.
Development exposes `/docs`, `/redoc`, and `/v2/openapi.json`; other environments explicitly return 404 for them.

`app/core/lifespan.py` manages the API lifecycle:

1. Create and validate the Redis client, and create the shared upstream HTTP client.
2. Bind Redis and assemble Endpoint, Runtime State, protocol admission, forwarding, cache, and public managers through
   `app/service_state.py`.
3. Initialize application cache and start the Redis Stream TaskIQ broker.
4. Connect Tortoise ORM without generating schema.
5. Start the JSON-RPC and HTTP API policy refresh loops and admission engines, the shared Health, Circuit, and
   Endpoint Tip dispatchers, and the Usage recorder.
6. On shutdown, stop accepting requests in reverse order, first drain the Usage recorder and the System Cache
   background publisher under deadlines, then drain dispatchers and admission engines, and finally close ORM, broker,
   cache, HTTP, and Redis clients.

API, Worker, and tests require reachable PostgreSQL and Redis services. Startup never creates database tables. Run
`make migrate` before the first deployment.

## Configuration loading

`app/core/config.py` resolves configuration in this order:

1. Process environment variables take precedence.
2. `ENV_FILE` may explicitly name a backend-specific dotenv file.
3. Without `ENV_FILE`, no dotenv file is loaded implicitly.
4. Relative `ENV_FILE` paths resolve from `server/`; absolute paths are used unchanged.

Root `.env.test` and `.env.prod` files inject environment variables through uv, Compose, or a process manager.
Pydantic does not parse them as backend-specific dotenv files, and the configuration model continues to reject unknown
fields in dedicated files. `.env.example` is only a variable contract and contains no real values.

`APP_ENV` defaults to `dev` and accepts only `dev`, `test`, or `prod`. `RELOAD=true` requires `WORKERS=1`.

Main configuration groups:

- App/runtime: `APP_ENV`, `PROJECT_NAME`, `HOST`, `PORT`, `WORKERS`, `RELOAD`
- Observability: `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, `OTEL_AUTH` (read only by the fastlog watcher)
- Public Gateway: `PUBLIC_RPC_API_BASE_URL`, `PUBLIC_RPC_GATEWAY_BASE_DOMAIN`
- HTTP/forwarding: `RPC_HTTP_*`, `JSONRPC_FORWARDING_*`, `HTTP_API_FORWARDING_*`
- Protocol admission: `PUBLIC_JSONRPC_RATE_LIMIT_*`, `PUBLIC_HTTP_API_RATE_LIMIT_*`
- System Cache: `SYSTEM_CACHE_*`
- Runtime State: `RUNTIME_HEALTH_DISPATCHER_*`, `RUNTIME_TIP_DISPATCHER_*`, `ENDPOINT_HEALTH_CHECK_*`
- Database/Redis: `ORM_URL`, `REDIS_URL`, `REDIS_*_TIMEOUT_SECONDS`
- TaskIQ: `TASKIQ_*`
- Tests: `TEST_ORM_URL`, `TEST_REDIS_URL`
- Outbound: `OUTBOUND_HTTP_*`, `OUTBOUND_PRIVATE_NETWORK_CIDRS`
- Authentication/secrets: `GOOGLE_OAUTH_*`, `AURPAY_OIDC_*`, `FRONTEND_AUTH_CALLBACK_URL`, `ADMIN_ALLOWED_EMAILS`,
  `AUTH_*`, `APP_API_KEY_MASTER_KEY`, `ENDPOINT_ACTIVE_KEY_VERSION`, `ENDPOINT_KEYRING`

See [`.env.example`](../../.env.example) for every variable and safe placeholder. Production requires a strong session
secret, App API Key master key, and an active Endpoint keyring. Endpoint URLs, Endpoint authentication secrets, and
Provider credentials use separate encryption purposes.

Background Runtime State and Usage writers have no dedicated write timeout and share
`REDIS_SOCKET_TIMEOUT_SECONDS`. Request-level waits and shutdown drains remain controlled by their own Runtime State
settings.

## Routing and dependency injection

`BaseRouter` wraps control-plane routes that declare `response_model` in the `UnifiedResponseModel` OpenAPI schema.
`DashRouter` and `PublicRouter` keep their call boundaries. Public protocols bypass the control-plane unified envelope
and let their protocol adapters produce responses.

The root router `app/api/router.py` registers:

- `/v2/*` control-plane routes;
- public JSON-RPC ingress; and
- public HTTP API ingress.

Public protocols resolve by Host/Transport and cannot claim control-plane routes by path alone. WebSocket is not
implemented yet; gRPC must run as a separate service process that reuses service-layer capabilities instead of
registering a FastAPI router.

Dependency providers live in `app/api/deps.py` and only retrieve the authenticated principal and assembled managers.
Business use cases and protocol orchestration stay in services, not FastAPI route functions.

AurPay login uses the standard OIDC Authorization Code Flow with mandatory PKCE S256, `state`, and `nonce`. The OIDC
client requests only the `openid profile email` identity scopes; wallet and payment permissions are not part of the RPC
Gateway login flow. After the callback validates the ID Token signature, issuer, audience, nonce, and access-token
hash, the RPC Gateway account is bound by the AurPay `sub`. On a first login without an account for the same email,
the system automatically creates an ordinary `USER` account with unchanged permissions; when an account with the same
email exists, it is bound instead. Existing Google login restrictions are unaffected.

## Services and data

Service classes may extend `Manager` to receive the lifecycle-bound Redis client. Services orchestrate use cases,
read and write PostgreSQL or Redis, and convert ORM rows to model objects. Public control-plane contracts use
Pydantic. High-frequency internal paths may use dataclasses or msgspec, with models centralized in `app/model/`.

Data-layer rules:

- Use Tortoise ORM with PostgreSQL. `ORM_URL` accepts only `postgres://` or `postgresql://`.
- ORM models live in `app/orm/`; Tortoise configuration lives in `app/infra/db.py`.
- Shared types such as `NANOIDField`, `TimestampMixin`, and `GuidMixin` live in `app/orm/mixin.py`.
- Manage migrations with `make migrate` and `make makemigrations`; do not maintain a second runtime DDL path.

## Responses and errors

Control-plane success responses normally use `UnifiedResponse`:

```jsonc
{ "msg": "ok", "data": {} }
```

Control-plane errors use an HTTP status with a compact body:

```jsonc
{ "success": false, "msg": "Resource not found." }
```

`app/core/exception.py` handles `APIError`, request validation errors, Starlette HTTP errors, and uncaught exceptions
in that order. Uncaught exceptions log a full traceback but return stable internal-error text. Public JSON-RPC and
HTTP API use their own protocol error contracts instead of the control-plane envelope.

## TaskIQ, observability, and tests

`app/infra/broker.py` always uses Redis Stream. Workers register tasks explicitly from `jobs/registry.py`. Scheduler
uses `LabelScheduleSource`, and exactly one Scheduler instance may run per deployment.

```bash
make worker
make scheduler
```

API, TaskIQ Worker, and TaskIQ Scheduler log through `fastlog` to both stderr and separate log files. The
`fastlog-watcher` in Compose reads those files from a shared volume and exports OTLP Logs under the
`rpc-gateway:${APP_ENV}` service namespace; a persisted offset keeps sending after a watcher restart. OTel spans,
metrics, response trace propagation, and OTel TaskIQ trace propagation are not enabled, and the existing `A-Trace-ID`
and TaskIQ log context remain independent.

Tests use pytest and anyio. Database tests create an isolated schema through `TEST_ORM_URL`. Redis tests require an
explicit nonzero database and clean up by test prefix. Run tests directly related to a change by default rather than
full coverage for documentation or narrowly scoped edits.
