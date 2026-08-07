#!/usr/bin/env python3
"""Trim only the acknowledged prefix of a TaskIQ Redis Stream.

The script is dry-run by default. Apply mode requires the consumer group state
to remain unchanged while trimming so pending and undelivered tasks stay intact.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import CONF
from redis.asyncio import Redis
from redis.exceptions import RedisError

DEFAULT_CONSUMER_GROUP = 'taskiq'
DEFAULT_BATCH_SIZE = 1000
ATOMIC_TRIM_SCRIPT = """
local stream = KEYS[1]
local expected_groups = cjson.decode(ARGV[1])
local boundary = ARGV[2]
local approximate = ARGV[3] == '1'
local batch_size = tonumber(ARGV[4])

local function normalized(value)
    if value == nil or value == false or value == cjson.null then
        return ''
    end
    return tostring(value)
end

local rows = redis.call('XINFO', 'GROUPS', stream)
if #rows ~= #expected_groups then
    return {0, 'consumer group count changed'}
end

local actual_groups = {}
for _, row in ipairs(rows) do
    local metadata = {}
    for index = 1, #row, 2 do
        metadata[tostring(row[index])] = row[index + 1]
    end

    local name = tostring(metadata['name'])
    local pending = tonumber(metadata['pending'])
    local oldest_pending_id = nil
    if pending > 0 then
        local summary = redis.call('XPENDING', stream, name)
        oldest_pending_id = summary[2]
    end
    actual_groups[name] = {
        last_delivered_id = metadata['last-delivered-id'],
        pending = pending,
        oldest_pending_id = oldest_pending_id,
        lag = metadata['lag'],
    }
end

for _, expected in ipairs(expected_groups) do
    local actual = actual_groups[expected['name']]
    if actual == nil then
        return {0, 'consumer group names changed'}
    end
    if normalized(actual.last_delivered_id) ~= normalized(expected['last_delivered_id']) then
        return {0, 'last-delivered-id changed'}
    end
    if actual.pending ~= tonumber(expected['pending']) then
        return {0, 'pending count changed'}
    end
    if normalized(actual.oldest_pending_id) ~= normalized(expected['oldest_pending_id']) then
        return {0, 'oldest pending ID changed'}
    end
    if normalized(actual.lag) ~= normalized(expected['lag']) then
        return {0, 'consumer group lag changed'}
    end
end

local removed
if approximate then
    removed = redis.call('XTRIM', stream, 'MINID', '~', boundary, 'LIMIT', batch_size)
else
    removed = redis.call('XTRIM', stream, 'MINID', '=', boundary)
end
return {1, removed}
"""


class StreamCleanupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupState:
    name: str
    last_delivered_id: str
    pending: int
    oldest_pending_id: str | None
    lag: int | None

    @property
    def boundary(self) -> str:
        return self.oldest_pending_id or self.last_delivered_id


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamState:
    stream: str
    length: int
    memory_bytes: int | None
    used_memory: int | None
    used_memory_dataset: int | None
    groups: tuple[GroupState, ...]
    boundary: str


def _stream_id_key(value: str) -> tuple[int, int]:
    try:
        milliseconds, sequence = value.split('-', maxsplit=1)
        return int(milliseconds), int(sequence)
    except (TypeError, ValueError) as exc:
        raise StreamCleanupError(f'Invalid Redis Stream ID: {value!r}.') from exc


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('Value must be greater than zero.')
    return parsed


def _group_value(group: dict[str, Any], key: str) -> Any:
    if key not in group:
        raise StreamCleanupError(f'Consumer group metadata is missing {key!r}.')
    return group[key]


async def _load_group_state(redis: Redis, stream: str, group: dict[str, Any]) -> GroupState:
    name = str(_group_value(group, 'name'))
    pending = int(_group_value(group, 'pending'))
    last_delivered_id = str(_group_value(group, 'last-delivered-id'))
    lag_value = group.get('lag')
    lag = int(lag_value) if lag_value is not None else None
    oldest_pending_id: str | None = None
    if pending:
        summary = await redis.xpending(stream, name)
        if not isinstance(summary, dict) or summary.get('min') is None:
            raise StreamCleanupError(f'Pending summary is invalid for consumer group {name!r}.')
        oldest_pending_id = str(summary['min'])
    return GroupState(
        name=name,
        last_delivered_id=last_delivered_id,
        pending=pending,
        oldest_pending_id=oldest_pending_id,
        lag=lag,
    )


async def load_stream_state(redis: Redis, stream: str, expected_groups: tuple[str, ...]) -> StreamState:
    key_type = await redis.type(stream)
    if key_type != 'stream':
        raise StreamCleanupError(f'Redis key {stream!r} is not a Stream.')

    group_rows = await redis.xinfo_groups(stream)
    if not isinstance(group_rows, list):
        raise StreamCleanupError('Consumer group metadata is invalid.')
    groups = tuple([await _load_group_state(redis, stream, group) for group in group_rows])
    group_names = {group.name for group in groups}
    expected_group_names = set(expected_groups)
    if group_names != expected_group_names:
        expected_names = sorted(expected_group_names)
        actual_names = sorted(group_names)
        raise StreamCleanupError(
            f'Consumer groups changed or differ from expectation: expected {expected_names}, got {actual_names}.'
        )
    if not groups:
        raise StreamCleanupError('At least one consumer group is required.')

    boundary = min((group.boundary for group in groups), key=_stream_id_key)
    if boundary == '0-0':
        raise StreamCleanupError('The safe trim boundary is 0-0.')

    memory_info = await redis.info('memory')
    memory_bytes = await redis.memory_usage(stream)
    return StreamState(
        stream=stream,
        length=int(await redis.xlen(stream)),
        memory_bytes=int(memory_bytes) if memory_bytes is not None else None,
        used_memory=int(memory_info['used_memory']) if 'used_memory' in memory_info else None,
        used_memory_dataset=int(memory_info['used_memory_dataset']) if 'used_memory_dataset' in memory_info else None,
        groups=tuple(sorted(groups, key=lambda group: group.name)),
        boundary=boundary,
    )


def _check_frozen_groups(before: StreamState, after: StreamState) -> None:
    if before.groups != after.groups or before.boundary != after.boundary:
        raise StreamCleanupError('Consumer group state changed during cleanup.')


async def _trim_batch(redis: Redis, state: StreamState, *, approximate: bool, batch_size: int) -> int:
    expected_groups = json.dumps([asdict(group) for group in state.groups], separators=(',', ':'), sort_keys=True)
    # Reason: redis-py stubs include a synchronous branch; the asyncio client returns an awaitable.
    result = await redis.eval(  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
        ATOMIC_TRIM_SCRIPT,
        1,
        state.stream,
        expected_groups,
        state.boundary,
        '1' if approximate else '0',
        batch_size,
    )
    if not isinstance(result, list) or len(result) != 2:
        raise StreamCleanupError('Atomic Stream trim returned an invalid response.')
    if int(result[0]) != 1:
        raise StreamCleanupError(f'Consumer group state changed before trim: {result[1]}.')
    return int(result[1])


async def trim_stream(
    redis: Redis,
    *,
    stream: str,
    expected_groups: tuple[str, ...],
    batch_size: int,
    exact: bool,
) -> tuple[StreamState, StreamState, int]:
    """Trim entries older than the frozen safe boundary.

    Side effects:
        Removes Redis Stream entries that precede every consumer group's oldest
        pending or last-delivered message.
    """

    before = await load_stream_state(redis, stream, expected_groups)
    removed = 0
    while True:
        batch_removed = await _trim_batch(redis, before, approximate=True, batch_size=batch_size)
        removed += batch_removed
        if batch_removed == 0:
            break

    if exact:
        removed += await _trim_batch(redis, before, approximate=False, batch_size=batch_size)
    after = await load_stream_state(redis, stream, expected_groups)
    _check_frozen_groups(before, after)
    return before, after, removed


def _state_payload(state: StreamState) -> dict[str, object]:
    return asdict(state)


async def run_cleanup(
    *,
    redis_url: str,
    stream: str,
    expected_groups: tuple[str, ...],
    batch_size: int,
    apply: bool,
    exact: bool,
) -> dict[str, object]:
    redis = Redis.from_url(redis_url, decode_responses=True, retry_on_timeout=False)
    try:
        before = await load_stream_state(redis, stream, expected_groups)
        if not apply:
            return {'mode': 'dry-run', 'before': _state_payload(before)}
        before, after, removed = await trim_stream(
            redis,
            stream=stream,
            expected_groups=expected_groups,
            batch_size=batch_size,
            exact=exact,
        )
        return {
            'mode': 'apply',
            'exact': exact,
            'removed': removed,
            'before': _state_payload(before),
            'after': _state_payload(after),
        }
    finally:
        await redis.aclose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Safely trim acknowledged TaskIQ Redis Stream history.')
    parser.add_argument('--stream', default=CONF.PROJECT_NAME)
    parser.add_argument('--group', action='append', dest='groups')
    parser.add_argument('--batch-size', type=_positive_int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument('--apply', action='store_true', help='Apply the trim. The default mode only prints the safe boundary.')
    parser.add_argument('--exact', action='store_true', help='Finish with an unbounded exact trim after approximate batches.')
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.exact and not args.apply:
        parser.error('--exact requires --apply.')
    expected_groups = tuple(args.groups or [DEFAULT_CONSUMER_GROUP])
    try:
        result = asyncio.run(
            run_cleanup(
                redis_url=CONF.REDIS_URL,
                stream=args.stream,
                expected_groups=expected_groups,
                batch_size=args.batch_size,
                apply=args.apply,
                exact=args.exact,
            )
        )
    except (RedisError, StreamCleanupError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
