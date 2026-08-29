# Runtime State

Runtime State v2 lives in `app/model/runtime_state/` and `app/services/runtime_state/`. Ownership is divided by state;
there is no generic cross-domain runtime store:

```text
runtime_state/
├── endpoint/
│   ├── health/       # Endpoint request reachability and protocol validity
│   └── tip/          # Endpoint chain-tip observations
├── chain/
│   └── tip/          # Chain Tip aggregated from multiple Endpoint observations
└── circuit/          # Endpoint-level call admission state
```

## Endpoint Health

Health accepts only normalized `HealthObservation` values produced by the data plane or by an explicit manual check.
Each process uses a bounded dispatcher grouped by Endpoint, version, and 10-second time bucket. Redis retains a
60-second window and one snapshot per Endpoint while rejecting stale versions and observations.

JSON-RPC and HTTP API forwarding submit a non-blocking observation for every real Endpoint call. A valid protocol
response is successful; each adapter classifies transport, authentication, configuration, timeout, server, and
protocol failures. A Health write failure must not change the user response.

Data-plane Health, Circuit, Window, Tip, and Usage writers set no dedicated short Redis deadline and use the shared
Redis client socket timeout as their final I/O bound. Operations that wait for a result, such as Circuit admission and
manual Health checks, retain their own request deadlines. Dispatcher drain deadlines bound process shutdown
separately.

A manual Health check is one fixed, non-retried Endpoint request explicitly initiated through the control plane. It
may wait for its dispatcher write, but it does not create a scheduler, a recurring probe, or an automatic probe task.

Health latency and Health Status are observational only. They do not participate in candidate filtering, load-balancing
weights, Tip, Tip Lag, limit, or Circuit decisions.

## Circuit Breaker

Circuit state is isolated by Endpoint, version, and workload class. It accepts only caller-classified
`CircuitObservation` values and never parses raw requests or responses. JSON-RPC forwarding classifies `debug_*` and
`trace_*` as `trace`; all other requests and HTTP API calls use `standard`.

- Closed retains consecutive connection-class hard failures. A separate lossy dispatcher aggregates successes and
  sampled failures into a 30-second Redis window. Results and window writes are non-blocking. The circuit opens only
  after at least 20 samples and a failure rate of at least 50%.
- Open rejects requests with exponential backoff.
- Half-open allows one real user request across the cluster and rejects stale or duplicate results through an epoch
  and probe token.
- HTTP 425 and 429 apply bounded `Retry-After` cooldowns without affecting the error rate or exponential backoff.
  Responses exceeding the local size limit do not indicate an unhealthy Endpoint and do not enter Circuit failure
  state.

Python computes transitions against the shared Redis clock. Redis uses a minimal CAS update for the single state.
An in-process cache must not let Open state outlive the shared `retry_at`. Sliding windows sample only in Closed. Both
opening and returning to Closed change generation so stale buckets cannot immediately reopen a recovered circuit.
Circuit creates no active probes; the window dispatcher aggregates only real traffic observations and fails open on
write errors.

## Endpoint Tip and Chain Tip

The Endpoint Tip dispatcher, Redis store, protocol extractors, and Chain Tip aggregator are implemented. Tip accepts
only normalized `TipObservation` values produced by protocol adapters. Chain Tip reads fresh Endpoint Tips per
dimension and computes a shared median under a bounded source count and a distributed lease. It produces no aggregate
when fewer than `MIN_TIP_SOURCES` sources are available; the current minimum is three.

`service_state.py` creates the Endpoint Tip manager and dispatcher. The dispatcher starts with the API lifecycle and
drains under a deadline during shutdown. Only Admin JSON-RPC forwarding submits an extractable Tip from the final
successful Endpoint. Explicit consumers and verification scripts construct the Chain Tip store and manager. System
Cache does not read Tip state. Reorg handling remains a separate follow-up capability.

## Dependency rules

Runtime State must not import public services, JSON-RPC or HTTP API forwarding, System Cache, Route ORM, or Endpoint
ORM. Forwarding may read Health/Circuit and submit Endpoint Tip in one direction. System Cache and Tip Runtime State
remain independent. Any future chain-consistency or Tip Lag signal must first become a normalized routing signal; the
Tip manager must not enter the forwarding loop directly.
