# System Cache

This document defines the runtime boundary, configuration, storage, cleanup, and stress verification of the V2 shared
System Cache. It is an internal development and operations document, not a public caching contract. See the
[JSON-RPC data plane](./architecture/jsonrpc-data-plane.md) and
[HTTP API data plane](./architecture/http-api-data-plane.md) for protocol integration.

## Request lifecycle

Each public protocol first completes its own Host resolution, admission, request parsing, authentication, and Gateway
validation, then loads the immutable route plan. System Cache runs between plan loading and execution of the caller's
plan:

1. Every Account may read an existing shared result. A JSON-RPC hit reuses the raw `result` with the current request
   ID; an HTTP hit reconstructs the original status, allowed headers, and body.
2. A User, or a plan without an executable target, reads Cache only. After a miss it executes the caller's own plan
   without publishing a shared result or submitting Endpoint Tip.
3. For an Admin with an executable plan, Cache binds the immutable plan already loaded for this request as the miss
   loader. A successful result is published according to policy, and Tip is submitted from the final successful
   Endpoint. The loader never discovers a producer through another Admin Gateway.
4. Once the Admin loader has executed, its result is returned even when a protocol error, identity validation failure,
   or cache write failure prevents publication. Endpoint must not be called twice. JSON-RPC Notifications always
   bypass Cache.

Cache failures fail open for an existing executable plan. A cache write failure does not replace the Admin loader's
successful result returned to the caller; JSON-RPC errors, Notifications, non-200 HTTP responses, and invalid
responses are never written to cache.

## Sharing boundary and policy

A cache key contains Transport, Chain, Network, operation, and normalized request identity, digested with 20-byte
BLAKE2b. Keys exclude Account, App, Gateway, API Key, and JSON-RPC ID, so every result admitted by policy must be safe
to share across tenants.

Currently admitted methods and parameter shapes:

| Protocol | Tier | Methods and constraints |
|------|------|------------|
| EVM | Redis TTL | `eth_blockNumber` with omitted parameters or `[]` |
| EVM | PostgreSQL retention | `eth_getBlockByNumber` at an explicit hexadecimal height with `false` as the second parameter; `debug_traceBlockByNumber` at an explicit height with `callTracer` and `tracerConfig.withLog=true` |
| SVM | Redis TTL | `getSlot` and `getLatestBlockhash` with default parameters or `commitment=finalized` only |
| SVM | PostgreSQL retention | `getBlock` at an explicit slot with `commitment=finalized`, `rewards=false`, `json` or `jsonParsed` encoding only, and transaction version `0` only |
| UTXO | Redis TTL | `getblockchaininfo` with default parameters; `getblockhash` with one nonnegative height |
| UTXO | PostgreSQL retention | `getblock` with a block hash and verbosity `3`; the response hash must match the request |
| TRON | Redis TTL | `eth_blockNumber` with omitted parameters or `[]` |
| TRON HTTP API | Redis TTL | `POST /wallet/getnodeinfo` with no query and no body; the response must contain a valid `solidityBlock` |
| TRON HTTP API | PostgreSQL retention | `POST /wallet/getblockbynum` with no query and a body containing only a nonnegative integer `num` and `visible=true`; the response block height must match |

System Cache does not read Endpoint Tip, Chain Tip, or chain-consistency state. Once an Admin executable plan returns
a success that matches policy, it is published directly; the PostgreSQL retention tier and the height-addressed UTXO
Redis TTL tier require no Tip source or hash-to-height warmup. Chain reorganizations, forks, canonical rollbacks, and
their cache invalidation semantics are a separate follow-up capability and are not handled in this version.

## Configuration

System Cache is enabled by default and can be disabled by explicitly setting `false`. API, Worker, and Scheduler must
use identical settings and restart after a change; the Scheduler cleanup schedule is fixed when tasks are imported
during process startup.

| Setting | Default | Constraint and purpose |
|------|--------|------------|
| `SYSTEM_CACHE_ENABLED` | `true` | Enables shared reads and allows Admin requests to publish on a miss |
| `SYSTEM_CACHE_REDIS_TTL_MS` | `250` | Freshness for the ordinary Redis TTL tier, 20–60000 ms; height-addressed UTXO `getblockhash` uses per-chain retention; a fixed 5-second stale window also applies |
| `SYSTEM_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN` | Per-chain defaults | Must contain exactly every supported chain, each 60–604800 seconds |
| `ORM_POOL_MIN_SIZE` / `ORM_POOL_MAX_SIZE` | `1` / `5` | PostgreSQL pool for ordinary application queries |
| `SYSTEM_CACHE_POSTGRES_POOL_MIN_SIZE` / `SYSTEM_CACHE_POSTGRES_POOL_MAX_SIZE` | `1` / `8` | PostgreSQL pool for large cache payload I/O and expiry cleanup |
| `SYSTEM_CACHE_COORDINATION_POOL_MIN_SIZE` / `SYSTEM_CACHE_COORDINATION_POOL_MAX_SIZE` | `1` / `8` | PostgreSQL pool that coordinates identical requests across processes |

Example:

```dotenv
SYSTEM_CACHE_ENABLED=true
```

Default PostgreSQL retention: Ethereum 7200 seconds, Polygon 1200, BSC 600, Arbitrum 300, Optimism 1200, Base 1200,
Solana 1500, Bitcoin 86400, Litecoin 21600, and TRON 1200. An override must not provide only some chains.

## Storage and concurrency

- The Redis TTL tier lives in Redis. Its value contains payload, fresh and stale deadlines, and publisher fence, and
  its Redis TTL ends at the stale boundary.
- The PostgreSQL retention tier stores Zstd level 1 compressed payloads in `system_cache_payload`; `payload_size`
  records uncompressed bytes and `stored_size` records compressed bytes. The authoritative owner lease lives in
  `system_cache_payload_lease`, and both derived cache tables are UNLOGGED. Migration
  `0005_compress_system_cache_payload` clears only these two rebuildable tables, keeps no read path for old raw
  payloads, and leaves business tables untouched.
- Readability of the PostgreSQL retention tier follows `stored_at` and per-chain retention, and is not shortened by
  Tip or stability depth.
- Cache first merges identical requests by key within a process; different keys are no longer bound by an additional
  cache-internal loader limit. Each protocol's Inflight admission always limits the total number of concurrent
  requests per API process, and requests over that limit never reach Cache or Endpoint. At most 2048 same-key waiters
  may accumulate per process. Cache entries have no protocol-level per-entry size limit, and Endpoint responses, JSON
  parsing, serialization, and compression still create temporary copies.
- A successful same-process single-flight follower does not call Endpoint again and is recorded as a Cache Hit
  according to caller semantics, returning `X-RPC-Gateway-Cache: HIT`; the leader is still recorded as a Miss.
  Followers of a JSON-RPC error, Gateway failure, or empty result are not recorded as hits.
- Cross-process loading of the same key is merged per tier: Redis TTL uses a Redis token lease, and PostgreSQL
  retention uses a PostgreSQL per-key lease. Leases last 5 seconds and renew every second; the bound for waiting on
  another owner covers the maximum forwarding budget of JSON-RPC and HTTP API. After gaining ownership, the Endpoint
  loader uses its own full retry and timeout budget instead of inheriting the time left from the flight coordination
  phase.
- A successful PostgreSQL retention loader returns the raw result to the caller immediately, while compression and the
  fenced commit are completed by a background publisher. The publisher holds at most 64 payloads totaling 256 MiB,
  performs at most two writes concurrently, and has a five-second publication budget. Queue rejection or a background
  write failure drops only the cache publication and does not change the RPC response. Flight release no longer
  consumes the request's outer 100 ms budget and instead runs in a lifecycle-managed background task with its own
  one-second I/O budget.
- Ordinary application queries, retention payload I/O, and retention leases use three separate application pools that
  connect to the same PostgreSQL. Large payload transfers do not occupy the connections reserved for lease renewal and
  release, nor the ordinary connections used by login, routing, and similar queries. Capacity planning must sum the
  maximum sizes of all three pools across processes.
- Redis TTL leases derive microsecond fences from Redis TIME and enforce monotonicity within an instance lifetime; the
  commit Lua verifies the owner atomically. The clock must not move backwards after a Redis restart or failover.
  Retention acquire, renew, and release are short PostgreSQL statements; commit and refresh lock the lease row and
  verify token, fence, and `lease_until` in one statement without holding a transaction across upstream loading. An
  old owner arriving late cannot write even when the new owner has only acquired ownership and not yet published.
- A successful `eth_getBlockByNumber` response is published only when the returned `number` matches the requested
  height. A UTXO hash must be a valid string, and the `hash` of `getblock` must match the request. A mismatched result
  is still returned to the Admin caller of that request but does not pollute the shared cache. Solana slot and
  `blockHeight` are not the same sequence, so no incorrect equality is assumed.
- TRON HTTP `getnodeinfo` only validates the Solidity block height structure; `getblockbynum` additionally requires
  the response `block_header.raw_data.number` to equal the requested `num`. HTTP cache payloads use a dedicated binary
  envelope and do not reuse the JSON-RPC `result` format.
- This schema and binary change does not support rolling a mix of old and new API binaries. On deployment, stop the
  old API, Worker, and Scheduler, run migrations, then start all new replicas together. Migration
  `0008_system_cache_transport` clears old-format payload and lease data, adds the Transport dimension, and unifies
  the configuration prefix as `SYSTEM_CACHE_*` with no alias for the old `SYSTEM_JSONRPC_CACHE_*`; it involves no
  business data migration.

Production capacity is still controlled by per-chain retention and Scheduler cleanup; no capacity setting such as
`SYSTEM_CACHE_POSTGRES_CAPACITY_BYTES` is provided. Before a long local scan, stop old scanners, clear the derived
retention payload and lease caches, verify free disk space, and monitor it every minute; stop the test when free space
drops below 10 GiB. Do not carry the disk-watermark policy of local stress tests into production cache semantics.

## Retention job

When Cache is enabled, Scheduler submits `delete_expired_retained_entries` every 30 seconds. The job holds a 25-second
Redis lease, runs for at most 20 seconds and 32 batches, deletes at most 64 rows per batch, and rotates across Chains.
Worker and Scheduler must both run. A cleanup failure only logs a summary and retries on the next schedule without
entering the public protocol request path.

## Stress verification

Core mode does not access external Redis or PostgreSQL and suits quick checks after policy, flight, and memory
boundary changes:

```bash
make system-cache-stress ARGS='--mode core --profile quick'
```

Integration and all modes create and delete a temporary PostgreSQL schema and clean a dedicated Redis database. Use a
dedicated PostgreSQL database whose name contains `test`, and an explicit nonzero dedicated Redis database that is
empty before the run; pointing at the application database or the shared Redis DB 0 is forbidden.

```bash
make system-cache-stress \
  ARGS='--mode all --profile quick --redis-db 15 --postgres-database rpc_gateway_cache_test'
```

This example derives connections from `REDIS_URL` and `ORM_URL`. Redis DB 15 must be empty, and the
`rpc_gateway_cache_test` database must already exist and differ from the application database. Dedicated
`SYSTEM_CACHE_STRESS_REDIS_URL` and `SYSTEM_CACHE_STRESS_POSTGRES_URL` values or the corresponding CLI URL arguments
are also accepted. Integration and all modes initialize the three PostgreSQL pools for ordinary queries, retention
I/O, and request coordination, and verify that coordination can still acquire, renew, and release ownership while the
retention pool is saturated. The command emits a JSON report and exits nonzero on scenario assertion, resource
boundary, or cleanup failure.
