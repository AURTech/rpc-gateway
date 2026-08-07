# Rate limiter

`rpc-gateway-api` provides `pyrate-limiter` adapters in `app/middleware/limiter/`.

## Components

- `RateLimiter`: dependency-injected limiter backed by `pyrate_limiter.Limiter` for in-process counters.
- `WebSocketRateLimiter`: WebSocket equivalent of `RateLimiter`.
- `RedisRateLimiter`: dependency-injected limiter backed by `RedisBucket`; counters are stored in Valkey and shared
  across processes.
- `RedisWebSocketRateLimiter`: WebSocket equivalent of `RedisRateLimiter`.
- `RateLimiterMiddleware`: global middleware that applies one limit to a complete request path.

## Counter backends

`RateLimiter`, `WebSocketRateLimiter`, and `RateLimiterMiddleware` receive a `pyrate_limiter.Limiter` directly. Their
counters remain in the current process, making them suitable for tests, single-process services, or quotas that do
not need to span Uvicorn workers.

`RedisRateLimiter` and `RedisWebSocketRateLimiter` lazily create a `Limiter` with `RedisBucket`. They store counters in
Valkey through `request.app.state.redis` or `ws.app.state.redis`, so application lifecycle initialization must finish
before use.

## Dependency-injected interfaces

`RateLimiter` accepts:

- `limiter`: a `pyrate_limiter.Limiter`;
- `identifier`: async identifier function, defaulting to `default_identifier`;
- `callback`: over-limit callback, defaulting to `default_callback`;
- `blocking`: whether to wait for a token, default `False`; and
- `skip`: async predicate that bypasses this check when it returns `True`.

The default callback raises `RateLimitError`, which the global exception handler converts to the shared error format.

`RedisRateLimiter` accepts `rates: list[Rate]`, `bucket_key`, `identifier`, `callback`, `blocking`, and `skip`. Unlike
`RateLimiter`, it creates the underlying limiter lazily from rates, bucket key, and the Valkey-compatible client.

## Default behavior

The default identifier uses the proxy-sanitized `X-Real-IP`, then `request.client.host`, and finally `127.0.0.1`. The
resulting key is `ip:path`.

This requires a single trusted ingress. Nginx, Traefik, or another controlled reverse proxy must overwrite caller-
supplied `X-Real-IP` and `CF-IPCountry` values instead of forwarding or appending them. The API does not parse
`X-Forwarded-For` or `CF-Connecting-IP` directly. Reassess header trust before allowing untrusted clients or services
to connect to the API without the proxy.

Dependency-injected limiters and `RateLimiterMiddleware` return HTTP 429 with:

```json
{ "success": false, "msg": "Request too fast, please try again later." }
```

## Use in this repository

The generic `RedisRateLimiter` protects control-plane operations such as login and manual Endpoint Health checks.

Public JSON-RPC and HTTP API do not reuse that dependency. Protocol-neutral runtime primitives live in
`app/services/admission/`; policy and orchestration live in `app/services/jsonrpc_rate_limit/` and
`app/services/http_api_rate_limit/`:

- Each `RateLimitPolicyManager` owns PostgreSQL policy, versions, audit, and periodic cross-process refresh.
- `JsonRpcAdmissionManager` and `HttpApiAdmissionManager` define independent Inflight, Global/IP, and Account/App
  stages.
- `TokenBucketAdmissionEngine` and `InflightAdmissionLimiter` do not depend on ORM, FastAPI, Endpoint, or protocol
  forwarding.
- Global/IP checks run atomically before authentication; Account/App checks run atomically after authentication.
- Admission defaults to an all-or-none Lua token bucket in Valkey. When Valkey is unavailable, it uses a bounded local
  bucket split conservatively by Worker and expected replica count.
- Setting `PUBLIC_JSONRPC_RATE_LIMIT_BACKEND` or `PUBLIC_HTTP_API_RATE_LIMIT_BACKEND` to `local` bypasses shared Valkey
  admission. Local state resets on restart and cannot span workers or replicas, so it is valid only for one Worker and
  one replica.
- Policy defaults to `shadow`. Requests submit observations without waiting to a bounded queue; queue saturation or a
  Valkey error does not apply backpressure.
- JSON-RPC `max_inflight_per_worker` is an independent process safety bound and always runs in `disabled`, `shadow`, or
  `enforce`. The default is 64 concurrent requests per API process. Rejection maps to JSON-RPC `-32029` before Cache or
  Endpoint access. HTTP API concurrency follows its policy mode.
- JSON-RPC and HTTP API use separate namespaces, Valkey keys, queues, and fallback stores. Shadow and Enforce are also
  isolated within each protocol. Enforce maps synchronously to JSON-RPC `-32029` or HTTP 429 with `Retry-After` and
  starts with a fresh configured burst rather than inheriting Shadow tokens.

Administrators manage dynamic policies through `/v2/jsonrpc-rate-limit-policy` and
`/v2/http-api-rate-limit-policy`. Each protocol has one global policy. `PUBLIC_JSONRPC_RATE_LIMIT_EXPECTED_REPLICAS`
and `PUBLIC_HTTP_API_RATE_LIMIT_EXPECTED_REPLICAS` must match the deployed replica count.

Each Shadow dispatcher uses the matching `PUBLIC_*_RATE_LIMIT_SHADOW_*` settings. Queue drops, stale-policy drops, and
Valkey fallback affect observation completeness only. They do not change the user response or Enforce state. Only
background write failures and observations dropped during shutdown produce one warning each.

## Examples

Dependency-injected shared limiting:

```python
from fastapi import Depends, FastAPI
from pyrate_limiter import Duration, Rate

from app.middleware.limiter import RedisRateLimiter

app = FastAPI()
limiter = RedisRateLimiter(
    rates=[Rate(5, Duration.MINUTE)],
    bucket_key="ratelimit:api:default",
)


@app.get("/ping", dependencies=[Depends(limiter)])
async def ping():
    return {"msg": "pong"}
```

The application lifecycle must set `app.state.redis` before this dependency runs.

Global middleware limiting:

```python
from fastapi import FastAPI
from pyrate_limiter import Duration, Limiter, Rate

from app.middleware.limiter import RateLimiterMiddleware

app = FastAPI()
app.add_middleware(
    RateLimiterMiddleware,
    limiter=Limiter(Rate(2, Duration.SECOND * 60)),
)
```

Both middleware and dependency-injected limiters accept `skip(request)` and a custom over-limit callback. Tests cover
these contracts in `tests/test_limiter_middleware.py` and `tests/test_redis_limiter.py`.

The package exports WebSocket limiter adapters, but the application does not register a WebSocket route.
