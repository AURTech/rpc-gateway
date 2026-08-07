import asyncio
import base64
from dataclasses import dataclass

import asyncpg
import orjson
from app.infra import redis as redis_keys
from app.model.blockchain import Chain, Network
from app.model.runtime_state.circuit import CircuitSnapshot
from app.model.runtime_state.endpoint.health import EndpointHealth
from app.model.runtime_state.tip import Finality, TipUnit
from app.services.runtime_state.chain.tip import ChainTipManager, ChainTipStore
from app.services.runtime_state.circuit import CircuitManager
from app.services.runtime_state.endpoint.health import HealthManager
from app.services.runtime_state.endpoint.tip import TipManager
from app.services.runtime_state.endpoint.tip.store import TipStore
from app.services.system_jsonrpc_cache.codec import PayloadCodec
from redis.asyncio import Redis


@dataclass(frozen=True, slots=True, kw_only=True)
class TipAuditSpec:
    chain: Chain
    network: Network
    unit: TipUnit
    finality: Finality
    endpoint_ids: tuple[str, str, str]
    endpoint_values: tuple[int, int, int]
    expected_value: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PostgresRetentionAuditSpec:
    chain: Chain
    network: Network
    method: str
    expected_cache_key: str
    expected_sequence: int
    expected_result: object


@dataclass(frozen=True, slots=True, kw_only=True)
class RedisTtlAuditSpec:
    chain: Chain
    network: Network
    method: str
    expected_cache_key: str
    expected_result: object


class RuntimeInspector:
    def __init__(self, redis_url: str, postgres_url: str) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True, retry_on_timeout=False)
        self._postgres_url = postgres_url
        self._payload_codec = PayloadCodec()

    async def close(self) -> None:
        await self._redis.aclose()

    async def clear_redis_ttl(self) -> int:
        pattern = redis_keys.build_pattern('system_jsonrpc_cache', 'v1', 'redis_ttl', '*')
        keys = [str(key) async for key in self._redis.scan_iter(match=pattern, count=256)]
        return int(await self._redis.unlink(*keys)) if keys else 0

    async def audit_empty_baseline(self) -> dict[str, int]:
        patterns = {
            'endpoint_tip': redis_keys.build_pattern('runtime_state', 'v2', 'tip', '*'),
            'chain_tip': redis_keys.build_pattern('runtime_state', 'v2', 'chain', 'tip', '*'),
            'system_cache': redis_keys.build_pattern('system_jsonrpc_cache', 'v1', '*'),
        }
        counts: dict[str, int] = {}
        found: dict[str, list[str]] = {}
        for name, pattern in patterns.items():
            keys = [str(key) async for key in self._redis.scan_iter(match=pattern, count=256)]
            keys.sort()
            counts[name] = len(keys)
            if keys:
                found[name] = keys
        connection = await asyncpg.connect(self._postgres_url)
        try:
            retained_rows = int(await connection.fetchval('SELECT COUNT(*) FROM system_jsonrpc_cache_payload'))
        finally:
            await connection.close()
        counts['system_cache_postgres_retention'] = retained_rows
        if retained_rows:
            found['system_cache_postgres_retention'] = [str(retained_rows)]
        if found:
            raise RuntimeError(f'Integration runtime baseline is not empty: {found!r}.')
        return counts

    async def audit_admin_app(self, app_id: str) -> dict[str, str]:
        connection = await asyncpg.connect(self._postgres_url)
        try:
            row = await connection.fetchrow(
                """
                SELECT
                    app.id AS app_id,
                    app.account_id AS app_account_id,
                    account.id AS account_id,
                    account.role AS account_role,
                    account.status AS account_status
                FROM app
                JOIN account ON account.id = app.account_id
                WHERE app.id = $1 AND app.deleted_at IS NULL AND account.deleted_at IS NULL
                """,
                app_id,
            )
        finally:
            await connection.close()
        if (
            row is None
            or str(row['account_role']) != 'admin'
            or str(row['account_status']) != 'active'
            or str(row['app_account_id']) != str(row['account_id'])
        ):
            raise RuntimeError(f'Publisher App is not owned by an active Admin account: {app_id}.')
        return {
            'app_id': str(row['app_id']),
            'account_id': str(row['account_id']),
            'account_role': str(row['account_role']),
            'account_status': str(row['account_status']),
        }

    async def wait_endpoint_tip(
        self,
        *,
        endpoint_id: str,
        endpoint_version: int,
        expected_value: int,
        timeout_seconds: float = 5,
    ) -> dict[str, object]:
        manager = TipManager(TipStore(self._redis))
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            tip = await manager.get(
                endpoint_id=endpoint_id,
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                unit=TipUnit.BLOCK,
                finality=Finality.LATEST,
            )
            if tip is not None and tip.endpoint_version == endpoint_version and tip.value == expected_value:
                return {
                    'endpoint_id': tip.endpoint_id,
                    'endpoint_version': tip.endpoint_version,
                    'value': tip.value,
                    'observed_at': tip.observed_at.isoformat(),
                }
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    f'Endpoint Tip did not converge to version {endpoint_version} and value {expected_value}: {tip!r}.'
                )
            await asyncio.sleep(0.02)

    async def audit_cache_flights(self) -> int:
        return await self.audit_cache_flight_count(0)

    async def audit_cache_flight_count(self, expected: int) -> int:
        pattern = redis_keys.build_pattern('system_jsonrpc_cache', 'v1', 'flight', '*')
        keys = [str(key) async for key in self._redis.scan_iter(match=pattern, count=256)]
        if len(keys) != expected:
            raise RuntimeError(f'Expected {expected} System Cache flight keys, found {len(keys)}: {keys!r}.')
        return len(keys)

    async def audit_postgres_retention_absent(self, spec: PostgresRetentionAuditSpec) -> None:
        connection = await asyncpg.connect(self._postgres_url)
        try:
            count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM system_jsonrpc_cache_payload
                WHERE chain = $1 AND network = $2 AND method = $3 AND cache_key = $4
                """,
                spec.chain.value,
                spec.network.value,
                spec.method,
                spec.expected_cache_key,
            )
        finally:
            await connection.close()
        if count != 0:
            raise RuntimeError(f'System Cache unexpectedly retained rejected payload key {spec.expected_cache_key}.')

    async def audit_runtime(
        self,
        tip_specs: list[TipAuditSpec],
        bad_endpoints: list[tuple[str, int]],
        good_endpoints: list[tuple[str, int]],
    ) -> dict[str, object]:
        health_manager = HealthManager(self._redis)
        circuit_manager = CircuitManager(self._redis)
        tip_manager = TipManager(TipStore(self._redis))
        chain_manager = ChainTipManager(
            tip_manager,
            ChainTipStore(self._redis, max_redis_io_ms=5000),
        )
        await self._wait_health(health_manager, bad_endpoints, timeout_seconds=5)

        tip_rows: list[dict[str, object]] = []
        for spec in tip_specs:
            slot = f'{{tip|{spec.chain.value}|{spec.network.value}|{spec.unit.value}|{spec.finality.value}}}'
            prefix = ('runtime_state', 'v2', 'tip', slot)
            values_key = redis_keys.build_key(*prefix, 'values')
            index_key = redis_keys.build_key(*prefix, 'index')
            expiry_key = redis_keys.build_key(*prefix, 'expiry')
            # Reason: redis.asyncio cardinality commands are awaitable at runtime; stubs expose a sync branch.
            cardinalities = (
                int(await self._redis.hlen(values_key)),  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
                int(await self._redis.zcard(index_key)),  # pyright: ignore[reportGeneralTypeIssues]
                int(await self._redis.zcard(expiry_key)),  # pyright: ignore[reportGeneralTypeIssues]
            )
            if cardinalities != (3, 3, 3):
                raise RuntimeError(f'Tip cardinality mismatch for {spec.chain.value}: {cardinalities!r}.')
            observations = await tip_manager.list(
                chain=spec.chain,
                network=spec.network,
                unit=spec.unit,
                finality=spec.finality,
            )
            if {tip.endpoint_id for tip in observations} != set(spec.endpoint_ids):
                raise RuntimeError(f'Tip Endpoint identity mismatch for {spec.chain.value}.')
            expected_observations = dict(zip(spec.endpoint_ids, spec.endpoint_values, strict=True))
            actual_observations = {tip.endpoint_id: tip.value for tip in observations}
            if actual_observations != expected_observations:
                raise RuntimeError(
                    f'Tip Endpoint values mismatch for {spec.chain.value}: '
                    f'expected {expected_observations!r}, found {actual_observations!r}.'
                )
            chain_tip = await chain_manager.get_tip(
                chain=spec.chain,
                network=spec.network,
                unit=spec.unit,
                finality=spec.finality,
            )
            if chain_tip is None or chain_tip.source_count != 3 or chain_tip.value != spec.expected_value:
                raise RuntimeError(f'Chain Tip invariant failed for {spec.chain.value}.')
            tip_rows.append(
                {
                    'chain': spec.chain.value,
                    'sources': chain_tip.source_count,
                    'value': chain_tip.value,
                    'cardinalities': cardinalities,
                }
            )

        bad_rows: list[dict[str, object]] = []
        for endpoint_id, version in bad_endpoints:
            health = await health_manager.get(endpoint_id, version)
            circuit = await circuit_manager.get(endpoint_id, version)
            if health is None or health.status.value != 'unhealthy' or health.samples < 3:
                raise RuntimeError(f'Bad Endpoint Health invariant failed for {endpoint_id}.')
            if circuit.state.value != 'open' or circuit.failures < 5:
                raise RuntimeError(f'Bad Endpoint Circuit invariant failed for {endpoint_id}.')
            bad_rows.append(
                {
                    'endpoint_id': endpoint_id,
                    'health': health.status.value,
                    'samples': health.samples,
                    'circuit': circuit.state.value,
                    'failures': circuit.failures,
                }
            )

        healthy = 0
        for endpoint_id, version in good_endpoints:
            health = await health_manager.get(endpoint_id, version)
            if health is not None and health.status.value == 'healthy' and health.samples > 0:
                healthy += 1
        if healthy != len(good_endpoints):
            raise RuntimeError(f'Only {healthy}/{len(good_endpoints)} good Endpoints became healthy.')

        lock_pattern = redis_keys.build_pattern('runtime_state', 'v2', 'chain', 'tip', '*', 'lock')
        locks = [str(key) async for key in self._redis.scan_iter(match=lock_pattern, count=128)]
        if locks:
            raise RuntimeError(f'Chain Tip left {len(locks)} lock keys behind.')
        fence_pattern = redis_keys.build_pattern('runtime_state', 'v2', 'chain', 'tip', '*', 'fence')
        fence_keys = [str(key) async for key in self._redis.scan_iter(match=fence_pattern, count=128)]
        expected_fence_keys = {
            redis_keys.build_key(
                'runtime_state',
                'v2',
                'chain',
                'tip',
                f'{{{spec.chain.value}|{spec.network.value}|{spec.unit.value}|{spec.finality.value}}}',
                'fence',
            )
            for spec in tip_specs
        }
        if set(fence_keys) != expected_fence_keys:
            raise RuntimeError(
                f'Chain Tip fence dimensions mismatch: expected {sorted(expected_fence_keys)!r}, found {sorted(fence_keys)!r}.'
            )
        fence_values = [int(value or 0) for value in await self._redis.mget(fence_keys)]
        if any(value <= 0 for value in fence_values):
            raise RuntimeError('Chain Tip fence values must be positive.')
        return {
            'tips': tip_rows,
            'bad_endpoints': bad_rows,
            'healthy_endpoints': healthy,
            'orphan_tip_locks': 0,
            'chain_tip_fences': len(fence_keys),
            'chain_tip_fence_min': min(fence_values),
        }

    async def audit_cache(
        self,
        expected_postgres_retention: list[PostgresRetentionAuditSpec],
        expected_redis_ttl: list[RedisTtlAuditSpec],
    ) -> dict[str, object]:
        redis_ttl_pattern = redis_keys.build_pattern('system_jsonrpc_cache', 'v1', 'redis_ttl', '*')
        redis_ttl_keys = [str(key) async for key in self._redis.scan_iter(match=redis_ttl_pattern, count=256)]
        expected_redis_ttl_keys = {
            redis_keys.build_key(
                'system_jsonrpc_cache',
                'v1',
                'redis_ttl',
                spec.chain.value,
                spec.network.value,
                spec.method,
                spec.expected_cache_key,
            ): spec
            for spec in expected_redis_ttl
        }
        if set(redis_ttl_keys) != set(expected_redis_ttl_keys):
            raise RuntimeError(
                f'System Cache Redis TTL keys mismatch: expected {sorted(expected_redis_ttl_keys)!r}, '
                f'found {sorted(redis_ttl_keys)!r}.'
            )
        ttls = [int(await self._redis.pttl(key)) for key in redis_ttl_keys]
        if any(ttl <= 0 for ttl in ttls):
            raise RuntimeError('System Cache Redis TTL invariant failed.')
        redis_ttl_values = await self._redis.mget(redis_ttl_keys)
        redis_ttl_fences: list[int] = []
        for key, raw in zip(redis_ttl_keys, redis_ttl_values, strict=True):
            try:
                value = orjson.loads(raw)
                redis_ttl_fences.append(int(value['publisher_fence']))
                payload = base64.b64decode(value['payload'], validate=True)
            except (KeyError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
                raise RuntimeError('System Cache Redis TTL publisher fence is invalid.') from exc
            expected_payload = orjson.dumps(expected_redis_ttl_keys[key].expected_result)
            if payload != expected_payload:
                raise RuntimeError(f'System Cache Redis TTL payload mismatch for {key}.')
        if any(fence <= 0 for fence in redis_ttl_fences):
            raise RuntimeError('System Cache Redis TTL publisher fences must be positive.')
        flight_pattern = redis_keys.build_pattern('system_jsonrpc_cache', 'v1', 'flight', '*')
        flight_keys = [str(key) async for key in self._redis.scan_iter(match=flight_pattern, count=256)]
        if flight_keys:
            raise RuntimeError(f'System Cache left {len(flight_keys)} flight keys behind.')

        connection = await asyncpg.connect(self._postgres_url)
        try:
            rows = await connection.fetch(
                """
                SELECT chain, network, method, cache_key, sequence, payload, payload_size, stored_size, publisher_fence
                FROM system_jsonrpc_cache_payload
                """
            )
        finally:
            await connection.close()
        if len(rows) != len(expected_postgres_retention):
            raise RuntimeError(
                f'Expected exactly {len(expected_postgres_retention)} PostgreSQL retention rows, found {len(rows)}.'
            )
        retention_report: list[dict[str, object]] = []
        for spec in expected_postgres_retention:
            matching = [
                row
                for row in rows
                if str(row['chain']) == spec.chain.value
                and str(row['network']) == spec.network.value
                and str(row['method']) == spec.method
                and str(row['cache_key']) == spec.expected_cache_key
            ]
            if len(matching) != 1:
                raise RuntimeError(
                    f'Expected one retained System Cache payload for {spec.chain.value}/{spec.method}, found {len(matching)}.'
                )
            row = matching[0]
            saved_payload = row['payload']
            if not isinstance(saved_payload, bytes | bytearray | memoryview):
                raise RuntimeError(f'System Cache payload bytes are invalid for {spec.chain.value}/{spec.method}.')
            stored_bytes = bytes(saved_payload)
            expected_bytes = orjson.dumps(spec.expected_result)
            if row['stored_size'] != len(stored_bytes) or row['payload_size'] != len(expected_bytes):
                raise RuntimeError(f'System Cache stored bytes mismatch for {spec.chain.value}/{spec.method}.')
            payload_bytes = await self._payload_codec.decompress(stored_bytes, expected_size=row['payload_size'])
            if payload_bytes != expected_bytes:
                raise RuntimeError(f'System Cache decompressed bytes mismatch for {spec.chain.value}/{spec.method}.')
            if row['sequence'] != spec.expected_sequence:
                raise RuntimeError(f'System Cache stored sequence mismatch for {spec.chain.value}/{spec.method}.')
            if not isinstance(row['publisher_fence'], int) or row['publisher_fence'] <= 0:
                raise RuntimeError(f'System Cache publisher fence is invalid for {spec.chain.value}/{spec.method}.')
            try:
                decoded = orjson.loads(payload_bytes)
            except orjson.JSONDecodeError as exc:
                raise RuntimeError(f'System Cache payload cannot be decoded for {spec.chain.value}/{spec.method}.') from exc
            if decoded != spec.expected_result:
                raise RuntimeError(f'System Cache decoded payload mismatch for {spec.chain.value}/{spec.method}.')
            retention_report.append(
                {
                    'chain': spec.chain.value,
                    'network': spec.network.value,
                    'method': spec.method,
                    'cache_key': str(row['cache_key']),
                    'sequence': row['sequence'],
                    'payload_bytes': len(payload_bytes),
                    'stored_bytes': len(stored_bytes),
                    'publisher_fence': row['publisher_fence'],
                    'content_verified': True,
                }
            )
        return {
            'redis_ttl_keys': len(redis_ttl_keys),
            'redis_ttl_min_ms': min(ttls),
            'redis_ttl_fence_min': min(redis_ttl_fences),
            'postgres_retention': retention_report,
            'orphan_flights': 0,
        }

    async def _wait_health(
        self,
        manager: HealthManager,
        endpoints: list[tuple[str, int]],
        *,
        timeout_seconds: float,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            values = await manager.get_many(endpoints)
            if all(value is not None and value.status.value == 'unhealthy' for value in values.values()):
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError('Health observations did not converge before the deadline.')
            await asyncio.sleep(0.05)

    async def circuit_snapshot(self, endpoint_id: str, endpoint_version: int) -> CircuitSnapshot:
        return await CircuitManager(self._redis).get(endpoint_id, endpoint_version)

    async def endpoint_health(self, endpoint_id: str, endpoint_version: int) -> EndpointHealth | None:
        return await HealthManager(self._redis).get(endpoint_id, endpoint_version)
