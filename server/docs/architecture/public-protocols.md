# Public protocol boundaries

This document defines shared public data-plane capabilities and protocol isolation rules. See
[`README.md`](../../README.md) for the overview.

## Module responsibilities

Public Gateway code lives in `app/model/public/` and `app/services/public/`. It provides shared protocol operations:

- Host/Transport to Chain/Network resolution;
- Path Key, Bearer Key, and dual-credential consistency checks;
- App API Key lookup as an immutable `PublicGatewayIdentity`; and
- Gateway lookup and state validation from identity and address as an immutable `PublicGatewayContext`.

`PublicGatewayAccessManager.authenticate()` handles identity only. `get_context()` handles Gateway context only.
Public Access does not own admission, parse protocol bodies, load route plans, or call Endpoints.

`DatabasePublicIdentityLookup` and `DatabasePublicGatewayLookup` are read-only adapters. They return identity or
snapshot values without exposing ORM rows, API Key digests, database exceptions, or control-plane `APIError` values.

## Protocol lifecycle

Public JSON-RPC and HTTP API share Public Access and Endpoint Access. Each protocol owns its ingress, admission engine,
policy tables, routes, forwarding, and error mapping:

```text
Public JSON-RPC
  → Host(JSONRPC)
  → JSON-RPC Inflight / Global / IP Admission
  → JSON-RPC parse
  → Public identity
  → JSON-RPC Account / App Admission
  → Gateway context
  → System Cache / JSON-RPC Forwarding
  → Endpoint Access

Public HTTP API
  → Host(HTTP_API)
  → HTTP API Inflight / Global / IP Admission
  → Tron HTTP API parse
  → Public identity
  → HTTP API Account / App Admission
  → Gateway context
  → System HTTP API Cache / HTTP API Forwarding
  → Endpoint Access
```

The request remains inside the Inflight context for its entire lifecycle. Pre-authentication Global/IP admission
consumes tokens before parsing a protocol body or path, preventing malformed requests from bypassing admission.
Account/App admission runs only after identity succeeds.

## Sharing and isolation

The dependency direction is fixed:

```text
Public protocol → Public Access / protocol Admission → protocol Forwarding → Endpoint
```

- Lookup, admission engine, cache, forwarding, Runtime State, and Endpoint modules must not depend on a public
  protocol manager.
- JSON-RPC and HTTP API use separate Redis namespaces, Shadow queues, fallback stores, policies, and audits, and share
  neither quotas nor runtime state.
- The System Cache core handles only opaque payloads carrying a Transport, single-flight, and storage. JSON-RPC and
  HTTP API reach it through the `system_jsonrpc_cache` and `system_http_api_cache` facades, and the two protocol
  modules must not import each other.
- Protocol adapters own stable error and response contracts; Endpoint Access exposes only protocol-neutral outbound
  results and failure codes.
- The Gateway control plane continues to generate public addresses through `access_points`; the data plane does not
  copy control-plane management behavior.

The implemented protocol modules are `services/public/jsonrpc/` and `services/public/http_api/`. HTTP API is currently
limited to Tron. WebSocket and gRPC are not implemented, and no placeholder modules are created for them.
