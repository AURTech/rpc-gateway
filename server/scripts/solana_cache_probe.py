import argparse
import asyncio
import os
import time
from dataclasses import dataclass

import httpx
import orjson

CACHE_HEADER = 'X-RPC-Gateway-Cache'
COMMITMENT = 'finalized'
SCAN_BATCH_SIZE = 12
SCAN_INTERVAL_SECONDS = 10.0


@dataclass(frozen=True, slots=True, kw_only=True)
class ScannerResult:
    name: str
    slots: frozenset[int]
    block_requests: int
    block_hits: int


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError('Duration must be positive.')
    return seconds


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Verify Solana block cache behavior with two identical scanners.')
    parser.add_argument(
        '--gateway-url',
        default=os.environ.get('SOLANA_CACHE_PROBE_URL', ''),
        help='Gateway JSON-RPC URL. Defaults to SOLANA_CACHE_PROBE_URL.',
    )
    parser.add_argument('--duration', type=_positive_seconds, default=30.0, help='Probe duration in seconds.')
    args = parser.parse_args()
    if not args.gateway_url:
        parser.error('--gateway-url or SOLANA_CACHE_PROBE_URL is required.')
    return args


async def _call_rpc(client: httpx.AsyncClient, gateway_url: str, method: str, params: list[object]) -> tuple[object, bool]:
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    response = await client.post(gateway_url, json=payload)
    response.raise_for_status()
    decoded = orjson.loads(response.content)
    if not isinstance(decoded, dict):
        raise RuntimeError(f'{method} returned a non-object JSON-RPC response.')
    error = decoded.get('error')
    if error is not None:
        raise RuntimeError(f'{method} returned a JSON-RPC error.')
    result = decoded.get('result')
    if result is None:
        raise RuntimeError(f'{method} returned no result.')
    return result, response.headers.get(CACHE_HEADER) == 'HIT'


async def _get_slot(client: httpx.AsyncClient, gateway_url: str) -> int:
    result, _cache_hit = await _call_rpc(client, gateway_url, 'getSlot', [{'commitment': COMMITMENT}])
    if isinstance(result, bool) or not isinstance(result, int):
        raise RuntimeError('getSlot returned an invalid slot.')
    return result


async def _get_block(client: httpx.AsyncClient, gateway_url: str, slot: int) -> bool:
    options: dict[str, object] = {
        'encoding': 'jsonParsed',
        'rewards': False,
        'commitment': COMMITMENT,
        'maxSupportedTransactionVersion': 0,
    }
    _result, cache_hit = await _call_rpc(client, gateway_url, 'getBlock', [slot, options])
    return cache_hit


async def _sleep_until_poll(deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining > 0:
        await asyncio.sleep(min(SCAN_INTERVAL_SECONDS, remaining))


async def _scan(name: str, gateway_url: str, deadline: float, start: asyncio.Event) -> ScannerResult:
    limits = httpx.Limits(max_connections=SCAN_BATCH_SIZE, max_keepalive_connections=SCAN_BATCH_SIZE)
    timeout = httpx.Timeout(connect=6.0, read=12.0, write=6.0, pool=6.0)
    slots: set[int] = set()
    block_hits = 0
    async with httpx.AsyncClient(limits=limits, timeout=timeout, http2=False) as client:
        await start.wait()
        next_slot = await _get_slot(client, gateway_url)
        while time.monotonic() < deadline:
            latest_slot = await _get_slot(client, gateway_url)
            if latest_slot < next_slot:
                await _sleep_until_poll(deadline)
                continue

            batch_tail = min(latest_slot, next_slot + SCAN_BATCH_SIZE - 1)
            batch_slots = tuple(range(next_slot, batch_tail + 1))
            hits = await asyncio.gather(*(_get_block(client, gateway_url, slot) for slot in batch_slots))
            slots.update(batch_slots)
            block_hits += sum(hits)
            next_slot = batch_tail + 1
            if batch_tail >= latest_slot:
                await _sleep_until_poll(deadline)

    return ScannerResult(name=name, slots=frozenset(slots), block_requests=len(slots), block_hits=block_hits)


def _summary(results: tuple[ScannerResult, ScannerResult]) -> str:
    first, second = results
    overlap = first.slots & second.slots
    unique_slots = first.slots | second.slots
    block_requests = first.block_requests + second.block_requests
    block_hits = first.block_hits + second.block_hits
    hit_rate = block_hits / block_requests if block_requests else 0.0
    return (
        f'{first.name}: requests={first.block_requests}, hits={first.block_hits}; '
        f'{second.name}: requests={second.block_requests}, hits={second.block_hits}; '
        f'total_requests={block_requests}, unique_slots={len(unique_slots)}, overlap={len(overlap)}, '
        f'hits={block_hits}, hit_rate={hit_rate:.1%}'
    )


def _validate_hits(results: tuple[ScannerResult, ScannerResult]) -> None:
    first, second = results
    overlap = first.slots & second.slots
    if not overlap:
        raise RuntimeError('The scanners did not request any overlapping Solana slots.')
    hits = first.block_hits + second.block_hits
    if hits < len(overlap):
        raise RuntimeError(f'Expected at least {len(overlap)} cache hits for overlapping slots, observed {hits}.')


async def _run_probe(gateway_url: str, duration: float) -> tuple[ScannerResult, ScannerResult]:
    start = asyncio.Event()
    deadline = time.monotonic() + duration
    tasks = (
        asyncio.create_task(_scan('scanner-1', gateway_url, deadline, start)),
        asyncio.create_task(_scan('scanner-2', gateway_url, deadline, start)),
    )
    start.set()
    first, second = await asyncio.gather(*tasks)
    return first, second


def main() -> None:
    args = _parse_args()
    try:
        results = asyncio.run(_run_probe(args.gateway_url, args.duration))
        print(_summary(results))
        _validate_hits(results)
    except (httpx.HTTPError, RuntimeError) as exc:
        raise SystemExit(f'Solana cache probe failed: {exc}') from exc


if __name__ == '__main__':
    main()
