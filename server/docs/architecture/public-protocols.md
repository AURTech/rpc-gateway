# Public protocol boundaries

This document defines shared public data-plane behavior and protocol isolation. See [`README.md`](../../README.md) for
the architecture overview.

## Module responsibilities

Public Gateway code lives in `app/model/public/` and `app/services/public/`. It provides shared protocol operations:

- Host/Transport to Chain/Network resolution;
- Path Key, Bearer Key, and dual-credential consistency checks;
- App API Key lookup as an immutable `PublicGatewayIdentity`; and
- Gateway lookup and state validation as an immutable `PublicGatewayContext`.

`PublicGatewayAccessManager.authenticate()` handles identity only. `get_context()` handles Gateway context only.
Public Access does not own admission, parse protocol bodies, load route plans, or call Endpoints.

`DatabasePublicIdentityLookup` and `DatabasePublicGatewayLookup` are read-only adapters. They return identity or
snapshot values without exposing ORM rows, API Key digests, database exceptions, or control-plane `APIError` values.

## Protocol lifecycle

Public JSON-RPC and HTTP API share Public Access and Endpoint Access. Each protocol owns its ingress, admission engine,
policy tables, routes, forwarding, and error mapping:

```text
Public JSON-RPC
  -> Host(JSONRPC)
  -> JSON-RPC Inflight / Global / IP Admission
  -> JSON-RPC parse
  -> Public identity
  -> JSON-RPC Account / App Admission
  -> Gateway context
  -> System JSON-RPC Cache / JSON-RPC Forwarding
  -> Endpoint Access

Public HTTP API
  -> Host(HTTP_API)
  -> HTTP API Inflight / Global / IP Admission
  -> Tron HTTP API parse
  -> Public identity
  -> HTTP API Account / App Admission
  -> Gateway context
  -> HTTP API Forwarding
  -> Endpoint Access
```

The request remains inside the Inflight context for its entire lifecycle. Pre-authentication Global/IP admission
consumes tokens before parsing a protocol body or path, preventing malformed requests from bypassing admission.
Account/App admission runs only after identity succeeds.

## Sharing and isolation

The dependency direction is fixed:

```text
Public protocol -> Public Access / protocol Admission -> protocol Forwarding -> Endpoint
```

- Lookup, admission engine, cache, forwarding, Runtime State, and Endpoint modules must not depend on a public
  protocol manager.
- JSON-RPC and HTTP API use separate Valkey namespaces, Shadow queues, fallback stores, policies, and audits.
- The System JSON-RPC Cache belongs only to JSON-RPC and must not cache HTTP API responses.
- Protocol adapters own stable error and response contracts; Endpoint Access exposes only protocol-neutral outbound
  results and failure codes.
- The Gateway control plane continues to generate public URLs through `access_points`; the data plane does not copy
  control-plane management behavior.

The implemented public protocol modules are `services/public/jsonrpc/` and `services/public/http_api/`. HTTP API is
currently limited to Tron.
