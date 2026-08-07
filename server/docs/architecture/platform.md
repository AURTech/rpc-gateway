# Platform and infrastructure

This document defines the FastAPI lifecycle, shared layering, and infrastructure contracts. See the
[JSON-RPC](./jsonrpc-data-plane.md) and [HTTP API](./http-api-data-plane.md) documents for protocol data planes, and
[`README.md`](../../README.md) for the overview.

## Application factory and lifecycle

`app/__init__.py` creates the FastAPI application and validates production safety settings before startup.
Development exposes `/docs`, `/redoc`, and `/v2/openapi.json`; other environments explicitly return 404 for them.

`app/core/lifespan.py` manages the API lifecycle:

1. Create and validate the Valkey client and shared upstream HTTP client.
2. Bind Valkey and assemble Endpoint, Runtime State, protocol admission, forwarding, cache, and public managers through
   `app/service_state.py`.
3. Initialize application cache and start the Valkey Stream TaskIQ broker.
4. Connect Tortoise ORM without generating schema.
5. Start protocol policy refresh and admission engines, shared Health, Circuit, and Endpoint Tip dispatchers, and the
   Usage recorder.
6. On shutdown, stop accepting requests, drain Usage and the System JSON-RPC Cache publisher under deadlines, then
   drain dispatchers and admission engines before closing ORM, broker, cache, HTTP, and Valkey clients.

API, Worker, and tests require reachable PostgreSQL and Valkey services. Startup never creates database tables. Run
`make migrate` before the first deployment.

## Configuration loading

`app/core/config.py` resolves configuration in this order:

1. Process environment variables take precedence.
2. `ENV_FILE` may name a backend-specific dotenv file.
3. Without `ENV_FILE`, no dotenv file is loaded implicitly.
4. Relative `ENV_FILE` paths resolve from `server/`; absolute paths are used unchanged.

Root `.env.test` and `.env.prod` files are injected by uv, Compose, or a process manager. Pydantic does not treat them
as backend-specific dotenv files, and the configuration model continues to reject unknown fields in dedicated files.
`.env.example` is a variable contract and contains no real values.

`APP_ENV` defaults to `dev` and accepts only `dev`, `test`, or `prod`. `RELOAD=true` requires `WORKERS=1`.

Main configuration groups:

- App/runtime: `APP_ENV`, `PROJECT_NAME`, `HOST`, `PORT`, `WORKERS`, `RELOAD`
- Public Gateway: `PUBLIC_RPC_API_BASE_URL`, `PUBLIC_RPC_GATEWAY_BASE_DOMAIN`
- HTTP/forwarding: `RPC_HTTP_*`, `JSONRPC_FORWARDING_*`, `HTTP_API_FORWARDING_*`
- Protocol admission: `PUBLIC_JSONRPC_RATE_LIMIT_*`, `PUBLIC_HTTP_API_RATE_LIMIT_*`
- System JSON-RPC Cache: `SYSTEM_JSONRPC_CACHE_*`
- Runtime State: `RUNTIME_HEALTH_DISPATCHER_*`, `RUNTIME_TIP_DISPATCHER_*`, `ENDPOINT_HEALTH_CHECK_*`
- Database/Valkey: `ORM_URL`, `REDIS_URL`, `REDIS_*_TIMEOUT_SECONDS`
- TaskIQ: `TASKIQ_*`
- Tests: `TEST_ORM_URL`, `TEST_REDIS_URL`
- Outbound: `OUTBOUND_HTTP_*`, `OUTBOUND_PRIVATE_NETWORK_CIDRS`
- Authentication/secrets: `GOOGLE_OAUTH_*`, `FRONTEND_AUTH_CALLBACK_URL`, `ADMIN_ALLOWED_EMAILS`, `AUTH_*`,
  `APP_API_KEY_MASTER_KEY`, `ENDPOINT_ACTIVE_KEY_VERSION`, `ENDPOINT_KEYRING`

See [`.env.example`](../../.env.example) for every variable and safe placeholder. Production requires strong session
and App API Key secrets plus an active Endpoint keyring. Endpoint URLs, Endpoint authentication secrets, and Provider
credentials use separate encryption purposes.

Background Runtime State and Usage writers share `REDIS_SOCKET_TIMEOUT_SECONDS` as their final write boundary.
Request waits and shutdown drains retain their own Runtime State deadlines.

## Routing and dependency injection

`BaseRouter` wraps control-plane routes that declare `response_model` in the `UnifiedResponseModel` OpenAPI schema.
`DashRouter` and `PublicRouter` keep their call boundaries. Public protocols bypass the control-plane envelope and let
their protocol adapters produce responses.

`app/api/router.py` registers:

- `/v2/*` control-plane routes;
- public JSON-RPC ingress; and
- public HTTP API ingress.

Public protocols resolve by Host/Transport and cannot claim control-plane routes by path alone.

Dependency providers live in `app/api/deps.py` and only retrieve the authenticated principal and assembled managers.
Business use cases and protocol orchestration stay in services, not FastAPI route functions.

## Services and data

Service classes may extend `Manager` to receive the lifecycle-bound Valkey client. Services orchestrate use cases,
read and write PostgreSQL or Valkey, and convert ORM rows to model objects. Public control-plane contracts use
Pydantic. High-frequency internal paths may use dataclasses or msgspec, with models centralized in `app/model/`.

Data-layer rules:

- Use Tortoise ORM with PostgreSQL. `ORM_URL` accepts only `postgres://` or `postgresql://`.
- ORM models live in `app/orm/`; Tortoise configuration lives in `app/infra/db.py`.
- Shared types such as `NANOIDField`, `TimestampMixin`, and `GuidMixin` live in `app/orm/mixin.py`.
- Manage migrations with `make migrate` and `make makemigrations`; do not maintain a second runtime DDL path.

## Responses and errors

Control-plane success responses normally use `UnifiedResponse`:

```json
{ "msg": "ok", "data": {} }
```

Control-plane errors use an HTTP status with a compact body:

```json
{ "success": false, "msg": "Resource not found." }
```

`app/core/exception.py` handles `APIError`, request validation, Starlette HTTP errors, and uncaught exceptions in that
order. Uncaught exceptions log a full traceback but return stable internal-error text. Public JSON-RPC and HTTP API
use their own protocol error contracts instead of the control-plane envelope.

## TaskIQ, observability, and tests

`app/infra/broker.py` uses Valkey Stream. Workers register tasks explicitly from `jobs/registry.py`. Scheduler uses
`LabelScheduleSource`, and exactly one Scheduler instance may run per deployment.

```bash
make worker
make scheduler
```

API and Worker log through `fastlog`. OTLP export, response trace propagation, and TaskIQ trace propagation are not
enabled.

Tests use pytest and anyio. Database tests create an isolated schema through `TEST_ORM_URL`. Valkey tests require an
explicit nonzero database and clean up by test prefix. Run tests directly related to a change by default rather than
full coverage for documentation or narrowly scoped edits.
