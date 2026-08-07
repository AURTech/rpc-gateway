# System JSON-RPC Cache

This internal development and operations document defines the V2 shared System JSON-RPC Cache runtime boundary,
configuration, storage, cleanup, and stress verification. It is not a public caching contract. See the
[JSON-RPC data plane](./architecture/jsonrpc-data-plane.md) for architecture dependencies.

## Request lifecycle

Public JSON-RPC completes Host resolution, Inflight and Global/IP admission, parsing, App API Key authentication,
Account/App admission, and Gateway state and Transport validation. Forwarding then loads the caller's immutable route
plan. System Cache runs between plan loading and execution:

1. Every Account may read an existing shared result. A hit returns raw JSON `result` bytes with the current request ID.
2. A User or a plan without an executable target reads Cache only. On a miss it executes its own plan without
   publishing a shared result or submitting Endpoint Tip.
3. For an Admin with an executable plan, Cache binds that already-loaded immutable plan as the miss loader. An
   eligible success publishes and submits Tip from the final successful Endpoint. The loader never discovers a
   producer through another Admin Gateway.
4. Once the Admin loader has executed, its result is returned even if a JSON-RPC error or cache write failure prevents
   publication. Endpoint must not be called twice. Notifications always bypass Cache.

Cache failures fail open for an executable plan. A cache write failure does not replace a successful Admin response.
JSON-RPC errors, Notifications, and invalid responses are never cached.

## Sharing policy

Keys contain Chain, Network, method, and normalized parameter identity, hashed with 20-byte BLAKE2b. They exclude
Account, App, Gateway, API Key, and JSON-RPC ID, so every admitted result must be safe to share across tenants.

| Protocol | Tier | Methods and constraints |
|---|---|---|
| EVM | Valkey TTL | `eth_blockNumber` with omitted parameters or `[]` |
| EVM | PostgreSQL retention | `eth_getBlockByNumber` at an explicit hexadecimal height with `false`; `debug_traceBlockByNumber` at an explicit height with `callTracer` only |
| SVM | Valkey TTL | `getSlot` and `getLatestBlockhash` with defaults or `commitment=finalized` only |
| SVM | PostgreSQL retention | `getBlock` at an explicit slot with `commitment=finalized`, `rewards=false`, `json` or `jsonParsed` encoding, and transaction version `0` only |
| UTXO | Valkey TTL | Default `getblockchaininfo`; `getblockhash` with one nonnegative height |
| UTXO | PostgreSQL retention | `getblock` with block hash and verbosity `3`; response hash must match the request |
| TRON | Valkey TTL | `eth_blockNumber` with omitted parameters or `[]` |

System Cache does not read Endpoint Tip, Chain Tip, or chain-consistency state. An eligible Admin success publishes
directly. PostgreSQL retention and height-addressed UTXO Valkey entries require no Tip source or hash-to-height warmup.

## Configuration

System Cache is enabled by default and may be disabled explicitly. API, Worker, and Scheduler must use identical
settings and restart after a change. Scheduler cleanup timing is fixed when tasks are imported during startup.

| Setting | Default | Constraint and purpose |
|---|---|---|
| `SYSTEM_JSONRPC_CACHE_ENABLED` | `true` | Enables shared reads and Admin publication on misses |
| `SYSTEM_JSONRPC_CACHE_REDIS_TTL_MS` | `250` | Freshness for normal Valkey TTL entries, 20-60000 ms; height-addressed UTXO uses chain retention; stale window is fixed at 5 seconds |
| `SYSTEM_JSONRPC_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN` | Per-chain defaults | Must contain every supported chain, each 60-604800 seconds |
| `ORM_POOL_MIN_SIZE` / `ORM_POOL_MAX_SIZE` | `1` / `5` | PostgreSQL pool for ordinary application queries |
| `SYSTEM_JSONRPC_CACHE_POSTGRES_POOL_MIN_SIZE` / `SYSTEM_JSONRPC_CACHE_POSTGRES_POOL_MAX_SIZE` | `1` / `8` | PostgreSQL pool for large cache payloads and cleanup |
| `SYSTEM_JSONRPC_CACHE_COORDINATION_POOL_MIN_SIZE` / `SYSTEM_JSONRPC_CACHE_COORDINATION_POOL_MAX_SIZE` | `1` / `8` | PostgreSQL coordination pool for cross-process requests |

```dotenv
SYSTEM_JSONRPC_CACHE_ENABLED=true
```

Default PostgreSQL retention in seconds: Ethereum 7200, Polygon 1200, BSC 600, Arbitrum 300, Optimism 1200, Base 1200,
Solana 1500, Bitcoin 86400, Litecoin 21600, and TRON 1200. Overrides must specify every chain.

## Storage and concurrency

- Valkey TTL values contain payload, fresh and stale deadlines, and publisher fence. Their Valkey TTL ends at the
  stale boundary.
- PostgreSQL retention stores Zstd level 1 payloads in `system_jsonrpc_cache_payload`. `payload_size` is uncompressed
  bytes; `stored_size` is compressed bytes. Authoritative leases live in `system_jsonrpc_cache_payload_lease`. Both
  derived cache tables are UNLOGGED. Migration `0005_compress_system_cache_payload` clears only these rebuildable
  tables and retains no raw-payload compatibility path.
- PostgreSQL readability depends on `stored_at` and per-chain retention, not Tip or stability depth.
- Single-flight merges identical keys within a process. Different keys have no additional cache loader limit.
  JSON-RPC `max_inflight_per_worker` always limits total requests per API process and defaults to 64. At most 2048
  same-key waiters may accumulate per process.
- A successful same-process follower does not call Endpoint again and records a Cache Hit with
  `X-RPC-Gateway-Cache: HIT`; the leader remains a Miss. Followers of errors, Gateway failures, or empty results are not
  hits.
- Cross-process coalescing uses a Valkey token lease for TTL entries and a PostgreSQL per-key lease for retention.
  Leases last five seconds and renew every second. Waiting uses the route budget derived from Endpoint timeout and
  `JSONRPC_FORWARDING_MAX_ATTEMPTS`. A loader that gains ownership receives its full retry and timeout budget.
- A successful PostgreSQL loader returns raw bytes immediately. A background publisher compresses and fenced-commits
  them. It holds at most 64 payloads and 256 MiB, performs at most two writes concurrently, and has a five-second
  publication budget. Queue rejection or a write failure drops only the cache publication. Flight release runs as a
  lifecycle-managed background task with its own one-second I/O budget.
- Ordinary queries, retention payload I/O, and retention leases use three pools connected to the same PostgreSQL.
  Capacity planning must sum the maximum sizes of all three pools across processes.
- Valkey TTL leases derive microsecond fences from Valkey TIME and enforce monotonicity within an instance lifetime.
  Commit Lua verifies the owner atomically. PostgreSQL acquire, renew, and release use short SQL statements; commit and
  refresh lock the lease row and verify token, fence, and `lease_until` in one statement without holding a transaction
  across upstream loading.
- EVM, UTXO, and SVM response identity checks prevent mismatched upstream data from entering shared storage while
  still returning that response to the Admin caller.
- Cache schema changes do not support mixed old and new API binaries. Stop API, Worker, and Scheduler, run migrations,
  then start all new replicas. Migration clears old-format payload and lease data without touching business tables.

Production capacity is controlled by per-chain retention and Scheduler cleanup. Before long local scans, stop stale
scanners, clear derived retention payload and lease caches, verify free disk space, and monitor it every minute. Stop
the test below 10 GiB free space.

## Retention job

When Cache is enabled, Scheduler submits `delete_expired_retained_entries` every 30 seconds. The job holds a 25-second
Valkey lease, runs for at most 20 seconds and 32 batches, deletes at most 64 rows per batch, and rotates across Chains.
Worker and Scheduler must both run. Cleanup failures log a summary and retry on the next schedule without entering the
JSON-RPC request path.

## Stress verification

Core mode requires no external Valkey or PostgreSQL:

```bash
make system-jsonrpc-cache-stress ARGS='--mode core --profile quick'
```

Integration and all modes create and delete a temporary PostgreSQL schema and clean a dedicated Valkey database. Use
only a PostgreSQL database whose name contains `test` and an explicit, empty, nonzero Valkey database.

```bash
make system-jsonrpc-cache-stress \
  ARGS='--mode all --profile quick --redis-db 15 --postgres-database rpc_gateway_cache_test'
```

This example derives connections from `REDIS_URL` and `ORM_URL`. Valkey DB 15 must be empty, and
`rpc_gateway_cache_test` must already exist and differ from the application database. Dedicated
`SYSTEM_JSONRPC_CACHE_STRESS_REDIS_URL` and `SYSTEM_JSONRPC_CACHE_STRESS_POSTGRES_URL` values or CLI URLs are also
accepted. Integration initializes all three PostgreSQL pools and verifies that coordination can still acquire, renew,
and release ownership while retention I/O is saturated. The command emits a JSON report and exits nonzero on scenario,
resource, or cleanup failure.
