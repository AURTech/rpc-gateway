from datetime import UTC, datetime

import pytest
from app.core.config import CONF, Config
from pydantic import ValidationError


def _config(*, stream_length: int = 250_000, retention_months: int = 3, fine_retention_hours: int = 48) -> Config:
    values = CONF.model_dump()
    values['USAGE_STREAM_MAX_LENGTH'] = stream_length
    values['USAGE_HOURLY_RETENTION_MONTHS'] = retention_months
    values['USAGE_FINE_RETENTION_HOURS'] = fine_retention_hours
    return Config.model_validate(values)


def test_usage_limits_default_to_bounded_values() -> None:
    assert Config.model_fields['USAGE_STREAM_MAX_LENGTH'].default == 250_000
    assert Config.model_fields['USAGE_HOURLY_RETENTION_MONTHS'].default == 3
    assert Config.model_fields['USAGE_FINE_RETENTION_HOURS'].default == 48
    config = _config()

    assert config.USAGE_STREAM_MAX_LENGTH == 250_000
    assert config.USAGE_HOURLY_RETENTION_MONTHS == 3
    assert config.USAGE_FINE_RETENTION_HOURS == 48


def test_usage_limits_reject_unbounded_values() -> None:
    with pytest.raises(ValidationError):
        _config(stream_length=250_001)
    with pytest.raises(ValidationError):
        _config(retention_months=4)
    with pytest.raises(ValidationError):
        _config(fine_retention_hours=23)
    with pytest.raises(ValidationError):
        _config(fine_retention_hours=169)


def test_rollup_cutover_requires_an_exact_hour() -> None:
    values = CONF.model_dump()
    values['USAGE_ASYNC_ROLLUP_CUTOVER_AT'] = datetime(2026, 8, 1, 0, 1, tzinfo=UTC)

    with pytest.raises(ValidationError, match='exact UTC hour'):
        Config.model_validate(values)
