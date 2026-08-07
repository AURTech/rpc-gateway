# Gateway integration flows

The Admin publisher flow first proves that its Tip and System Cache namespaces are empty, then creates disposable Admin and User Apps, Gateways, Routes, and deterministic good/bad Endpoints in a fresh PostgreSQL and Valkey environment. It verifies the publisher App's exact active Admin ownership, directs cache-miss requests through two DNS-identified API containers, checks exact Endpoint Tip and Chain Tip state, verifies Valkey TTL entries and PostgreSQL retention payload bytes plus publisher fences, runs concurrent single-flight and repeated TTL-crossing publisher rounds, rejects wrong-height upstream mutations, and executes the isolated Runtime State and System Cache stress suites. A mock ledger independently records request, params, and response SHA-256 digests plus start/finish ordering. The controlled Tip conflict holds an older Endpoint revision until a newer revision has been stored, then proves that the late old response cannot replace it.

```bash
cd server
make gateway-flow-integration ARGS='--profile quick --workers 2'
```

The JSON report is written under `../.integration-reports/`. A pass requires an active Admin-owned publisher App, exact API container peer identity, an exact conflict ledger, exact upstream load counts, exact PostgreSQL retention rows and Valkey TTL entry count, positive publisher/Chain Tip fences, no orphan flight or Chain Tip lock, successful late-owner fencing for Valkey and PostgreSQL, and cleanup. It also runs a six-round Usage qualification across both accounts, both API replicas, and all ten chains. The Usage oracle permits at most 2% loss before Valkey Stream admission, but requires unique admitted events, exact Stream-to-PostgreSQL aggregation, a fully drained backlog, metric invariants, account isolation, and exact summary/series/method/network/Gateway API results. This is a finite qualification with an eight-round Admin publisher window, not an unlimited production soak. It does not restart an API replica during the window: the runner has no Docker control plane and the host orchestrator currently waits synchronously for Compose, so restart recovery remains a separate qualification boundary.

The mock also exposes a high-fidelity Solana response at
`/run/{token}/jsonrpc/realistic/solana/{source}`. Its `getBlock` result follows the public mainnet `json` or `jsonParsed`
shape and deterministically targets a 10 MiB response. The ordinary `good` behavior remains intentionally small so routing and cache
qualifications do not turn into large-payload load tests. The realistic behavior advances its finalized slot from a fixed UTC reference
at roughly one slot per 400 ms, so the head remains monotonic across mock restarts.
