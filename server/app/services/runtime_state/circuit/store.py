import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.infra import redis
from app.model.runtime_state.circuit import CircuitWorkloadClass
from app.services.runtime_state.circuit.state import CircuitRecord, closed_record

type CircuitRaw = str | bytes | bytearray | None

_CAS_LUA = """
local stored = redis.call('GET', KEYS[1])
if not stored then
    stored = ''
end
if stored ~= ARGV[1] then
    local parts = redis.call('TIME')
    return {0, stored, parts[1], parts[2]}
end
if ARGV[2] == '' then
    redis.call('DEL', KEYS[1])
else
    redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
end
return {1, ARGV[2]}
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredCircuit:
    record: CircuitRecord
    raw: CircuitRaw


@dataclass(frozen=True, slots=True, kw_only=True)
class CasResult:
    applied: bool
    raw: CircuitRaw
    redis_now: datetime | None
    clock_anchor: float | None


def make_key(endpoint_id: str, endpoint_version: int, workload_class: CircuitWorkloadClass) -> str:
    if endpoint_version < 1:
        raise ValueError('Circuit Endpoint version must be positive.')
    if not endpoint_id or len(endpoint_id) > 64:
        raise ValueError('Circuit Endpoint id must contain between 1 and 64 characters.')
    return redis.build_key('runtime_state', 'v3', 'circuit', endpoint_id, str(endpoint_version), workload_class.value)


class CircuitStore:
    def __init__(self, redis_client: Redis, *, state_ttl_seconds: int) -> None:
        self._redis = redis_client
        self._state_ttl_seconds = state_ttl_seconds
        self._cas = redis_client.register_script(_CAS_LUA)

    async def read(
        self,
        key: str,
        *,
        endpoint_id: str,
        endpoint_version: int,
        workload_class: CircuitWorkloadClass,
    ) -> StoredCircuit:
        raw = _parse_raw(await self._redis.get(key))
        return self.parse(
            raw,
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            workload_class=workload_class,
        )

    def parse(
        self,
        raw: CircuitRaw,
        *,
        endpoint_id: str,
        endpoint_version: int,
        workload_class: CircuitWorkloadClass,
    ) -> StoredCircuit:
        record = _parse_record(
            raw,
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            workload_class=workload_class,
        )
        return StoredCircuit(record=record, raw=raw)

    async def get_time(self) -> tuple[datetime, float]:
        clock_anchor = time.monotonic()
        raw = await self._redis.time()
        return _redis_time(raw), clock_anchor

    async def compare_set(self, key: str, *, expected: CircuitRaw, added: CircuitRecord) -> CasResult:
        expected_value = '' if expected is None else bytes(expected) if isinstance(expected, bytearray) else expected
        clock_anchor = time.monotonic()
        raw = await self._cas(
            keys=[key],
            args=[expected_value, added.model_dump_json(), self._state_ttl_seconds],
        )
        applied, value, redis_now = _parse_cas(raw)
        return CasResult(
            applied=applied,
            raw=value,
            redis_now=redis_now,
            clock_anchor=None if applied else clock_anchor,
        )


def _parse_record(
    raw: CircuitRaw,
    *,
    endpoint_id: str,
    endpoint_version: int,
    workload_class: CircuitWorkloadClass,
) -> CircuitRecord:
    if raw is None:
        return closed_record(endpoint_id, endpoint_version, workload_class)
    try:
        record = CircuitRecord.model_validate_json(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('Circuit state data is invalid.') from exc
    if (
        record.endpoint_id != endpoint_id
        or record.endpoint_version != endpoint_version
        or record.workload_class is not workload_class
    ):
        raise RuntimeError('Circuit state identity is invalid.')
    if record.updated_at is None:
        raise RuntimeError('Circuit state update time is invalid.')
    return record


def _parse_raw(raw: object) -> CircuitRaw:
    if raw is None or isinstance(raw, str | bytes | bytearray):
        return raw
    raise RuntimeError('Circuit state data is invalid.')


def _parse_cas(raw: object) -> tuple[bool, CircuitRaw, datetime | None]:
    if not isinstance(raw, list | tuple) or len(raw) not in (2, 4) or raw[0] not in (0, 1):
        raise RuntimeError('Circuit CAS result is invalid.')
    value = _parse_raw(raw[1])
    applied = raw[0] == 1
    if applied:
        if len(raw) != 2:
            raise RuntimeError('Circuit CAS result is invalid.')
        return True, None if value in ('', b'') else value, None
    if len(raw) != 4:
        raise RuntimeError('Circuit CAS result is invalid.')
    _, _, seconds, micros = raw
    return False, None if value in ('', b'') else value, _redis_time((seconds, micros))


def _redis_time(raw: object) -> datetime:
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        raise RuntimeError('Redis returned an invalid circuit time.')
    seconds = _to_int(raw[0])
    micros = _to_int(raw[1])
    if seconds is None or seconds < 0 or micros is None or not 0 <= micros < 1_000_000:
        raise RuntimeError('Redis returned an invalid circuit time.')
    try:
        return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(microseconds=micros)
    except (ValueError, OverflowError, OSError) as exc:
        raise RuntimeError('Redis returned an invalid circuit time.') from exc


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str | bytes | bytearray):
        return None
    try:
        return int(value)
    except ValueError:
        return None
