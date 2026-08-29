# JSON-RPC data plane

This document defines dependency boundaries for JSON-RPC routes, forwarding, the System Cache, and protocol-specific
admission. See [Public protocol boundaries](./public-protocols.md) for shared public protocol behavior.

## Route control plane

JSON-RPC routes live in `app/model/jsonrpc_route/`, `app/orm/jsonrpc_route/`, and `app/services/jsonrpc_route/`. They
manage:

- the default Gateway route;
- exact method scopes;
- route strategy, retry policy, and maximum attempts; and
- Endpoint target bindings with versioned replacement.

Endpoint Chain, Network, and Protocol are creation-time identities and cannot be changed. A route target can reference
only a JSON-RPC Endpoint in the same Account, Chain, and Network. Endpoint deletion or archival and route saves must
use the shared reference query and lock order to preserve concurrency invariants.

## Forwarding data plane

`app/services/jsonrpc_forwarding/` does not read control-plane ORM state. It receives an immutable `JsonRpcRoutePlan`
through `JsonRpcRoutePlanProvider`, then:

1. Loads the caller's route plan.
2. Filters out candidates that are not enabled.
3. Selects an Endpoint through load balancing that draws randomly by relative weight, or through position-ordered
   priority failover.
4. Classifies the method as a `standard` or `trace` workload, applies the matching Circuit admission, and performs a
   bounded Endpoint call.
5. Applies the route retry policy before changing candidates.
6. Submits exactly one Circuit outcome and a non-blocking Health observation.

Health latency is observational only; Circuit is the single hard admission for runtime failure state. Valid JSON-RPC
success and error responses are both protocol-valid results. The JSON-RPC adapter classifies transport, HTTP,
authentication, configuration, and protocol failures into generic Circuit observations, keeping Runtime State
independent of JSON-RPC. Circuit rejection does not consume a route attempt. When every candidate is rejected, the
result maps to `-32004`; a failure after any real call maps to `-32005`. Tip does not directly affect routing.

Endpoint success parses only the JSON-RPC envelope. `result` remains validated raw JSON bytes. The public response
streams a reconstructed envelope, and the System Cache reuses the same bytes. Cache identity and Tip extraction decode
only required scalar or object fields instead of constructing the complete result model. Error responses still use
Pydantic to validate protocol fields.

The public ingress accepts a single JSON-RPC 2.0 request; batches are not supported yet.

## System Cache

The JSON-RPC cache facade lives in `app/model/system_jsonrpc_cache/` and `app/services/system_jsonrpc_cache/`, and uses
the protocol-neutral core in `app/model/system_cache/`, `app/orm/system_cache/`, and `app/services/system_cache/`. Keys
contain Transport, Chain, Network, operation, and normalized parameter identity. They exclude JSON-RPC ID and tenant
identity, so policy can admit only successful, non-Notification `result` values safe to share across Accounts, Apps,
and Gateways.

The call order is fixed:

1. Public Access and JSON-RPC admission complete.
2. Forwarding loads the caller's immutable route plan.
3. Every account may read an existing shared result. A User miss forwards through its own plan but never publishes.
4. When an Admin plan is executable, Cache binds it as the loader for this request. A result already executed but
   found ineligible is returned directly; Endpoint must not be called twice.
5. Without a plan or target, the caller may read existing Cache data. A miss returns the normal forwarding failure.

An Admin loader uses the request Account, Gateway, and immutable plan. It does not discover another Admin Gateway.
Admin forwarding submits the final successful Endpoint Tip; User forwarding does not. Cache hits do not produce Tip.
Forwarding does not depend on Cache. The JSON-RPC facade does not import HTTP API, and the protocol-neutral core
imports neither protocol model.

System Cache does not read Endpoint Tip or Chain Tip. Once an Admin success passes Cache policy and response identity
validation it may be published: the Redis TTL tier performs a fenced commit inside the request, while the PostgreSQL
retention tier only hands the result to a background publisher for compression and a fenced commit. PostgreSQL
publication is therefore best-effort: queue rejection or a background write error drops only that cache publication
and does not change the RPC response already returned. PostgreSQL readability follows per-chain retention. Cache
invalidation after a chain reorganization or fork is a separate follow-up capability.

A public JSON-RPC response includes `X-RPC-Gateway-Cache: HIT` when it reads existing storage or successfully reuses an
in-process single-flight result. Cold-cache leaders, reused errors, misses, ineligible results, protocol errors, and
Notification responses do not include the header.

See [System Cache](../system-cache.md) for storage, concurrency, retention jobs, and stress checks.

## Admission and rate limits

Protocol-neutral admission primitives live in `app/model/admission/` and `app/services/admission/`:

- `InflightAdmissionLimiter` owns the per-process concurrent request lifecycle.
- `TokenBucketAdmissionEngine` owns namespaces, atomic Redis token buckets, bounded local fallback, the Shadow
  dispatcher, and metrics.

The JSON-RPC vertical slice lives in `jsonrpc_rate_limit`: `JsonRpcAdmissionManager` defines the Inflight, Global/IP,
and Account/App stages, and `JsonRpcRateLimitPolicyManager` manages PostgreSQL policy, versions, audits, and
cross-process refresh.

The per-process JSON-RPC concurrency limit is always enforced and defaults to 64. It is independent of the
Shadow/Enforce mode used for requests per second. Cache therefore needs no separate loader concurrency limit and
cannot bypass publication because an internal cache capacity is full.

Buckets in one stage are consumed all-or-none. When Redis is unavailable, only the bounded local fallback split
conservatively by Worker and replica count is permitted. Shadow never applies backpressure. Enforce decides
synchronously and maps rejection to JSON-RPC `-32029` with `Retry-After`. Shadow and Enforce use separate keys and
fallback stores, so enabling Enforce does not inherit Shadow tokens.
