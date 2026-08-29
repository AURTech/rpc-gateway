# Rate limiter

`app/middleware/limiter/` provides generic `pyrate-limiter` adapters for **control-plane** interfaces. The public
JSON-RPC and HTTP API data planes do not use them; see
[The public data plane does not reuse this module](#the-public-data-plane-does-not-reuse-this-module) below.

## Components

| Export | Form | Counter location |
|------|------|----------|
| `RateLimiter` / `WebSocketRateLimiter` | Dependency injection, receives a `pyrate_limiter.Limiter` directly | Current process only, not shared across workers |
| `RedisRateLimiter` / `RedisWebSocketRateLimiter` | Dependency injection, lazily initializes a `RedisBucket` from `rates + bucket_key + redis client` | Redis, shared across processes and replicas |
| `RateLimiterMiddleware` | Global middleware | Depends on the `Limiter` passed in |

Constructor parameters, defaults, and types follow the signatures in `depends.py` and `limiter.py` and are not
repeated here. Every form supports conditional `skip(request)` and a custom `callback`. The Redis forms depend on
`request.app.state.redis` or `ws.app.state.redis`, which the default lifespan sets.

The repository currently uses only `RedisRateLimiter`: password login and password change in
`app/api/v2/auth/auth.py`, and the manual Endpoint health check in `app/api/v2/endpoint/endpoint.py`. The WebSocket
variants and `RateLimiterMiddleware` are exported but have no call sites.

## Default identifier and trust boundary

The default identifier function uses `X-Real-IP`, then `request.client.host`, and finally `127.0.0.1`. The resulting
key is `ip:path`, meaning counters are kept per source IP and path.

This behavior requires the deployment to establish a single trusted ingress: the API may be reached only through a
controlled reverse proxy such as Nginx or Traefik, and the proxy must overwrite caller-supplied `X-Real-IP` and
`CF-IPCountry` values instead of forwarding or appending them. The API does not parse `X-Forwarded-For` or
`CF-Connecting-IP` directly. Reassess the source-header trust mechanism before allowing clients or other untrusted
services to reach the API directly without the proxy.

## Over-limit response

The default callback raises `RateLimitError`, and `RateLimiterMiddleware` uses the equivalent
`_default_middleware_callback`. Both return `429 Too Many Requests` with the shared error body:

```json
{ "success": false, "msg": "Request too fast, please try again later." }
```

## The public data plane does not reuse this module

Protocol-neutral runtime primitives live in `app/services/admission/`; protocol policy and orchestration live in
`app/services/jsonrpc_rate_limit/` and `app/services/http_api_rate_limit/`:

- Each `RateLimitPolicyManager` owns PostgreSQL policy, versions, audit, and periodic cross-process refresh.
- `JsonRpcAdmissionManager` and `HttpApiAdmissionManager` define the Inflight, Global/IP, and Account/App stages of
  their protocol.
- `TokenBucketAdmissionEngine` and `InflightAdmissionLimiter` do not depend on ORM, FastAPI, Endpoint, or protocol
  forwarding.
- Global/IP is checked atomically before authentication; Account/App is checked atomically after authentication.
- The admission backend defaults to an all-or-none Lua token bucket in Redis per stage. When Redis is unavailable it
  switches to a bounded local token bucket split by Worker and expected replica count.
- `PUBLIC_JSONRPC_RATE_LIMIT_BACKEND` and `PUBLIC_HTTP_API_RATE_LIMIT_BACKEND` may be set explicitly to `local`, fully
  bypassing Redis admission. A local bucket exists only in the current API process, resets on restart, and cannot be
  shared across workers or replicas, so it suits only single-worker, single-replica deployments.
- Policy defaults to `shadow`. Requests submit observations to a bounded background queue without waiting; a full
  queue or a Redis failure does not apply backpressure to user requests.
- `max_inflight_per_worker` is an independent process safety bound for both JSON-RPC and HTTP API and is always
  enforced whether policy is `disabled`, `shadow`, or `enforce`. By default each API process handles at most 64
  concurrent requests per protocol. Requests over the limit do not reach authentication, cache, or Endpoint access and
  map to JSON-RPC `-32029` or HTTP 429 respectively.
- JSON-RPC and HTTP API use separate namespaces, Redis keys, queues, and fallback stores; Shadow and Enforce are also
  isolated within each protocol. After switching to `enforce`, the decision is synchronous and the protocol layer maps
  it to JSON-RPC `-32029` or HTTP 429 with `Retry-After`. Enforce does not inherit Shadow tokens and starts cold with
  the configured burst.

Administrators manage dynamic policies through `/v2/jsonrpc-rate-limit-policy` and `/v2/http-api-rate-limit-policy`.
Each protocol currently has one global policy, with no plans, billing quotas, or tenant overrides.
`PUBLIC_JSONRPC_RATE_LIMIT_EXPECTED_REPLICAS` and `PUBLIC_HTTP_API_RATE_LIMIT_EXPECTED_REPLICAS` must match the
deployed replica count.

The two Shadow dispatchers are bounded by the matching `PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_*` and
`PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_*` settings. Queue drops, stale-policy drops, and Redis fallback affect observation
completeness only. They do not change the user response or Enforce state and produce no logs; only background write
errors and the number of observations dropped during shutdown produce one warning each.

## Tests

- `tests/test_limiter_middleware.py`: basic middleware behavior, `skip`, and custom callbacks.
- `tests/test_redis_limiter.py`: Redis counters, cross-instance sharing, and isolation between buckets.
