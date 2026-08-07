from jobs.usage.usage import flush_gateway_usage, rollup_gateway_usage


def test_gateway_usage_flush_runs_every_five_seconds() -> None:
    assert flush_gateway_usage.labels['schedule'] == [{'interval': 5}]


def test_gateway_usage_rollup_runs_every_five_minutes() -> None:
    assert rollup_gateway_usage.labels['schedule'] == [{'interval': 300}]
