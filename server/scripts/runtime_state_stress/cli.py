import argparse


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('Value must be positive.')
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not parsed > 0:
        raise argparse.ArgumentTypeError('Value must be positive.')
    return parsed


def _rate(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError('Value must be between 0 and 1.')
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Stress Runtime State with real concurrent operations against an isolated Redis database.',
    )
    parser.add_argument(
        '--redis-url',
        help='Dedicated Redis URL with an explicit numeric DB path. Defaults only to RUNTIME_STATE_STRESS_REDIS_URL.',
    )
    parser.add_argument('--profile', choices=('quick', 'full', 'soak'), default='quick')
    parser.add_argument('--users', type=_positive_int, help='Concurrent user workers.')
    parser.add_argument('--endpoints', type=_positive_int, help='Endpoint sources, at most 10000.')
    parser.add_argument('--ops', type=_positive_int, help='Dispatcher submissions.')
    parser.add_argument('--chain-readers', type=_positive_int, help='Concurrent cold and warm Chain Tip readers.')
    parser.add_argument(
        '--renewal-seconds',
        type=_positive_float,
        help='Aggregation duration; defaults to 0.5s above the configured Redis I/O renew threshold.',
    )
    parser.add_argument('--soak-seconds', type=_positive_float, help='Override the mixed-load duration; soak defaults to 300s.')
    parser.add_argument('--sample-interval', type=_positive_float, default=0.25)
    parser.add_argument(
        '--outage-redis-url',
        default='redis://127.0.0.1:1/0',
        help='Known-unavailable Redis URL used only by the isolated outage scenario.',
    )
    parser.add_argument('--max-rss-mib', type=_positive_float, help='Fail if sampled process peak RSS exceeds this value.')
    parser.add_argument('--max-rss-growth-mib', type=_positive_float, help='Fail if sampled RSS growth exceeds this value.')
    parser.add_argument('--max-cpu-percent', type=_positive_float, help='Fail if process CPU exceeds this one-core percentage.')
    parser.add_argument('--max-redis-memory-mib', type=_positive_float, help='Fail if sampled Redis memory exceeds this value.')
    parser.add_argument(
        '--max-redis-cpu-percent', type=_positive_float, help='Fail if sampled Redis CPU exceeds this percentage.'
    )
    parser.add_argument('--max-task-growth', type=_positive_int, help='Fail if asyncio task growth exceeds this value.')
    parser.add_argument(
        '--max-rss-slope-mib-per-minute',
        type=_positive_float,
        help='Fail if the bounded RSS sample regression exceeds this growth rate.',
    )
    parser.add_argument(
        '--max-health-drop-rate',
        type=_rate,
        help='Fail if the mixed-load Health dispatcher drops more than this fraction of accepted observations.',
    )
    return parser.parse_args()
