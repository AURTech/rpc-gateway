# HTTP API data plane

This document defines the HTTP API route, forwarding, Tron adapter, and protocol-specific admission boundaries. See
[Public protocol boundaries](./public-protocols.md) for shared public protocol behavior.

## Protocol scope

The public HTTP API currently serves Tron Mainnet and Nile only. `app/services/public/http_api/tron.py` recognizes the
FullNode, SolidityNode, and TronGrid v1 path families. Public addresses, authentication, and error contracts are
documented in the public integration documentation.

The public HTTP API manager owns the protocol lifecycle and error mapping. The Tron adapter validates and normalizes
methods, paths, headers, query parameters, and bodies. Public Access resolves identity and Gateway context. Forwarding
does not parse public paths or produce the public error format.

## Route control plane

HTTP API routes live in `app/model/http_api_route/`, `app/orm/http_api_route/`, and `app/services/http_api_route/`.
Each Gateway owns one route; routes are not scoped by JSON-RPC method. A route stores:

- a `load_balance` or `priority_failover` strategy;
- endpoint targets, positions, and optional weights;
- maximum attempts and retry policy; and
- a version used for concurrent replacement conflict detection.

A target can reference only an `http_api` Endpoint in the same Account, Chain, and Network. Endpoint lifecycle checks
references through the route reference adapter; HTTP API route and ORM layers do not call back into the Endpoint
service.

## Forwarding data plane

`app/services/http_api_forwarding/` loads an immutable plan through `HttpApiRoutePlanProvider`, then:

1. Filters out candidates that are not enabled.
2. Selects candidates randomly by relative weight for load balancing, or by position for priority failover.
3. Applies Circuit as the single runtime failure admission for a candidate, then performs a bounded Endpoint Access
   call.
4. Performs bounded failover under both route and process attempt limits.
5. Records exactly one Circuit outcome for each real call and submits a Health observation.

`safe_only` retries only access failures known not to have produced a business result, plus upstream 3xx, 401, 403,
and 429 responses. It does not replay requests that may have had side effects after a timeout, an interrupted
response, or a 5xx response. `idempotent` also permits retries after timeouts, failed or oversized responses, 408,
425, and 5xx responses. When attempts are exhausted, the public layer returns the last upstream response if one was
received; otherwise it maps the failure to a stable gateway error.

The public layer preserves upstream status and body while returning only allowed response headers. It forwards only
headers accepted by the protocol adapter. Endpoint Access injects the Endpoint's own provider authentication and does
not accept caller-supplied substitutes.

## System HTTP API Cache

HTTP API reaches the protocol-neutral `app/services/system_cache/` through the dedicated
`app/services/system_http_api_cache/`. The HTTP module owns request classification, response identity validation, and
the HTTP response envelope. It does not import or construct JSON-RPC calls, responses, policies, or loaders.

Only two exact requests are cached today: `POST /wallet/getnodeinfo` without a body uses a short Redis TTL, and
`POST /wallet/getblockbynum` with a body containing a nonnegative `num` and `visible=true` uses PostgreSQL retention.
Every Account may read an existing result; only an Admin whose route has an executable target publishes after a miss.
A hit returns `X-RPC-Gateway-Cache: HIT`, and cache failures fail open.

## Admission and rate limits

HTTP API uses a dedicated `HttpApiAdmissionManager`, `HttpApiRateLimitPolicyManager`, PostgreSQL policy and audit
tables, Redis namespace, Shadow queue, and local fallback store. Its Inflight, Global/IP, and Account/App stages match
the JSON-RPC stages, but quotas and state remain isolated.

`max_inflight_per_worker` is the concurrency ceiling every API process always enforces, independent of the policy
`mode`. `mode` controls only the requests-per-second limits for Global/IP and Account/App. Requests over the
concurrency limit return HTTP 429 before authentication and Endpoint access.

The protocol-neutral `TokenBucketAdmissionEngine` provides all-or-none Redis token buckets, conservative local
fallback, Shadow/Enforce isolation, and bounded shutdown. The Tron adapter maps HTTP API enforcement to HTTP 429 for
the relevant path family and returns `Retry-After`.

HTTP API admission does not manage Endpoint capacity, upstream provider quotas, billing quotas, route selection, or
retry decisions.
