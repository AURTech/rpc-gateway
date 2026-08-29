import argparse
import asyncio
import json
import secrets
import time
from datetime import UTC, datetime

from app.model.blockchain import Chain, Network
from app.model.usage import DEFAULT_USAGE_STREAM_MAX_LENGTH, GatewayUsageEvent
from redis.asyncio import Redis

DEFAULT_MEMORY_LIMIT_MB = 500
DEFAULT_BATCH_SIZE = 1000


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('Value must be greater than zero.')
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Measure the bounded Usage Stream memory footprint.')
    parser.add_argument('--redis-url', required=True)
    parser.add_argument('--entries', type=_positive_int, default=DEFAULT_USAGE_STREAM_MAX_LENGTH)
    parser.add_argument('--max-memory-mb', type=_positive_int, default=DEFAULT_MEMORY_LIMIT_MB)
    parser.add_argument('--batch-size', type=_positive_int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args()


def _max_event() -> GatewayUsageEvent:
    return GatewayUsageEvent(
        event_id='e' * 64,
        account_id='a' * 21,
        app_id='p' * 21,
        gateway_id='g' * 21,
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        method='💥' * 256,
        started_at=datetime.now(UTC),
        successful=True,
        duration_ms=2**63 - 1,
        request_bytes=2**63 - 1,
        response_bytes=2**63 - 1,
        cache_eligible=True,
        cache_hit=True,
    )


async def _execute(args: argparse.Namespace) -> tuple[dict[str, object], bool]:
    redis = Redis.from_url(args.redis_url, decode_responses=False, retry_on_timeout=False)
    key = f'usage-memory-stress:{secrets.token_hex(12)}'
    payload = _max_event().model_dump_json(exclude_defaults=True).encode()
    started_at = time.monotonic()
    try:
        # Reason: redis.asyncio ping is awaitable at runtime; stubs include a synchronous branch.
        if not await redis.ping():  # pyright: ignore[reportGeneralTypeIssues]  # ty: ignore[invalid-await]
            raise RuntimeError('Redis is not reachable.')
        baseline = await redis.info('memory')
        baseline_memory = int(baseline['used_memory'])
        inserted = 0
        while inserted < args.entries:
            batch_size = min(args.batch_size, args.entries - inserted)
            pipeline = redis.pipeline(transaction=False)
            for _ in range(batch_size):
                pipeline.xadd(key, {'payload': payload})
            await pipeline.execute()
            inserted += batch_size

        memory = await redis.info('memory')
        stream_memory_value = await redis.memory_usage(key, samples=0)
        stream_memory = int(stream_memory_value or 0)
        used_memory = int(memory['used_memory'])
        memory_growth = max(0, used_memory - baseline_memory)
        memory_limit = args.max_memory_mb * 1_000_000
        success = stream_memory <= memory_limit and memory_growth <= memory_limit
        report: dict[str, object] = {
            'success': success,
            'entries': inserted,
            'payload_bytes': len(payload),
            'stream_memory_bytes': stream_memory,
            'redis_memory_growth_bytes': memory_growth,
            'max_memory_bytes': memory_limit,
            'stream_bytes_per_entry': stream_memory / inserted,
            'elapsed_seconds': round(time.monotonic() - started_at, 3),
        }
        return report, success
    finally:
        await redis.unlink(key)
        await redis.aclose()


def main() -> None:
    report, success = asyncio.run(_execute(_parse_args()))
    print(json.dumps(report, indent=2, sort_keys=True))
    if not success:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
