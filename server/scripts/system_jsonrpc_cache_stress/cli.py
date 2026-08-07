import argparse


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError('Value must be positive.')
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Stress the System JSON-RPC Cache with bounded concurrent scenarios.')
    parser.add_argument('--mode', choices=('core', 'integration', 'all'), default='all')
    parser.add_argument('--profile', choices=('quick', 'full'), default='quick')
    parser.add_argument('--concurrency', type=_positive_int, help='Override same-key concurrency.')
    parser.add_argument('--redis-url', help='Dedicated non-zero Redis DB; or SYSTEM_JSONRPC_CACHE_STRESS_REDIS_URL.')
    parser.add_argument('--redis-db', type=_positive_int, help='Derive a dedicated Redis DB from application REDIS_URL.')
    parser.add_argument(
        '--postgres-url',
        help='Dedicated PostgreSQL test database; or SYSTEM_JSONRPC_CACHE_STRESS_POSTGRES_URL.',
    )
    parser.add_argument('--postgres-database', help='Derive a dedicated test database URL from application ORM_URL.')
    return parser.parse_args()
