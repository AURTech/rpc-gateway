import argparse

import pytest
from scripts.usage_query_benchmark import _p95, _test_postgres_url


def test_benchmark_accepts_only_test_postgres_database() -> None:
    assert _test_postgres_url('postgresql://localhost/rpc_gateway_test') == 'postgresql://localhost/rpc_gateway_test'

    with pytest.raises(argparse.ArgumentTypeError, match='does not contain test'):
        _test_postgres_url('postgresql://localhost/rpc_gateway')
    with pytest.raises(argparse.ArgumentTypeError, match='must use postgres'):
        _test_postgres_url('sqlite:///rpc_gateway_test')


def test_benchmark_p95_uses_nearest_rank() -> None:
    assert _p95([float(value) for value in range(1, 11)]) == 10
