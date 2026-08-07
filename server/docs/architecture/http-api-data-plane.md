# HTTP API data plane

This document defines the HTTP API route, forwarding, Tron adapter, and protocol-specific admission boundaries. See
[Public protocol boundaries](./public-protocols.md) for shared public protocol behavior.

## Protocol scope

The public HTTP API currently serves Tron Mainnet and Nile. `app/services/public/http_api/tron.py` recognizes the
FullNode, SolidityNode, and TronGrid v1 path families.

The public HTTP API manager owns the protocol lifecycle and error mapping. The Tron adapter validates and normalizes
methods, paths, headers, query parameters, and bodies. Public Access resolves identity and Gateway context. Forwarding
does not parse public paths or produce the public error format.

## Route control plane

HTTP API routes live in `app/model/http_api_route/`, `app/orm/http_api_route/`, and
`app/services/http_api_route/`. Each Gateway owns one route; routes are not scoped by JSON-RPC method. A route stores:

- a `load_balance` or `priority_failover` strategy;
- endpoint targets, positions, and optional weights;
- minimum trust, maximum latency, maximum attempts, and retry policy; and
- a version used for concurrent replacement conflict detection.

A target can reference only an `http_api` Endpoint in the same Account, Chain, and Network. Endpoint lifecycle checks
references through the route reference adapter; HTTP API route and ORM layers do not call back into the Endpoint
service.

## Forwarding data plane

`app/services/http_api_forwarding/` loads an immutable plan through `HttpApiRoutePlanProvider`, then:

1. Filters candidates by enabled state, trust, and the explicit latency ceiling.
2. Uses weighted power-of-two choices with health and latency for load balancing, or position order for priority
   failover.
3. Applies Circuit admission and calls candidates through Endpoint Access.
4. Performs bounded failover under both route and process attempt limits.
5. Records exactly one Circuit outcome for each real call and submits a Health observation.

`safe_only` retries only access failures known not to have produced a business result, plus upstream 3xx, 401, 403,
and 429 responses. It does not replay requests after a timeout, interrupted response, or 5xx response when the request
may have had side effects. `idempotent` also permits retries after timeouts, failed or oversized responses, 408, 425,
and 5xx responses. When attempts are exhausted, the public layer returns the last upstream response if one exists;
otherwise it maps the failure to a stable gateway error.

The public layer preserves upstream status and body while returning only allowed response headers. It forwards only
headers accepted by the protocol adapter. Endpoint Access injects provider authentication and does not accept caller-
supplied substitutes.

HTTP API responses do not use the System JSON-RPC Cache.

## Admission and rate limits

HTTP API uses a dedicated `HttpApiAdmissionManager`, `HttpApiRateLimitPolicyManager`, PostgreSQL policy and audit
tables, Valkey namespace, Shadow queue, and local fallback store. Its Inflight, Global/IP, and Account/App stages match
the JSON-RPC stages, but quotas and state remain isolated.

The protocol-neutral `TokenBucketAdmissionEngine` provides all-or-none Valkey token buckets, conservative local
fallback, Shadow/Enforce isolation, and bounded shutdown. The Tron adapter maps HTTP API enforcement to HTTP 429 for
the relevant path family and returns `Retry-After`.

HTTP API admission does not manage Endpoint capacity, upstream provider quotas, billing quotas, route selection, or
retry decisions.
