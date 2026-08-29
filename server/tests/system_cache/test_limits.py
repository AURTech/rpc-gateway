import pytest
from app.services.system_cache.limits import flight_wait_seconds


@pytest.mark.parametrize(('max_attempts', 'expected_seconds'), [(1, 6), (3, 18), (10, 60)])
def test_flight_wait_matches_endpoint_attempt_bound(max_attempts: int, expected_seconds: float) -> None:
    assert flight_wait_seconds(max_attempts) == expected_seconds
