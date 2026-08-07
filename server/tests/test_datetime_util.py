from datetime import UTC, datetime, timedelta, timezone

from app.util import datetime as datetime_util


def test_now_utc_returns_timezone_aware_utc_datetime() -> None:
    value = datetime_util.now_utc()

    assert value.tzinfo is UTC


def test_next_utc_timestamp_is_strictly_newer_than_future_version() -> None:
    previous = datetime_util.now_utc() + timedelta(seconds=1)

    assert datetime_util.next_utc_timestamp(previous) == previous + timedelta(microseconds=1)


def test_floor_utc_hour_converts_to_utc_hour_boundary() -> None:
    value = datetime(2026, 5, 8, 16, 30, 45, 123, tzinfo=timezone(timedelta(hours=8)))

    assert datetime_util.floor_utc_hour(value) == datetime(2026, 5, 8, 8, tzinfo=UTC)


def test_ceil_utc_hour_keeps_exact_utc_hour_boundary() -> None:
    value = datetime(2026, 5, 8, 8, tzinfo=UTC)

    assert datetime_util.ceil_utc_hour(value) == datetime(2026, 5, 8, 8, tzinfo=UTC)


def test_ceil_utc_hour_rounds_partial_hour_up() -> None:
    value = datetime(2026, 5, 8, 16, 1, tzinfo=timezone(timedelta(hours=8)))

    assert datetime_util.ceil_utc_hour(value) == datetime(2026, 5, 8, 9, tzinfo=UTC)


def test_five_minute_boundaries_normalize_to_utc() -> None:
    value = datetime(2026, 5, 8, 16, 33, 1, tzinfo=timezone(timedelta(hours=8)))

    assert datetime_util.floor_utc_five_minutes(value) == datetime(2026, 5, 8, 8, 30, tzinfo=UTC)
    assert datetime_util.ceil_utc_five_minutes(value) == datetime(2026, 5, 8, 8, 35, tzinfo=UTC)


def test_ceil_five_minutes_keeps_exact_boundary() -> None:
    value = datetime(2026, 5, 8, 8, 30, tzinfo=UTC)

    assert datetime_util.ceil_utc_five_minutes(value) == value


def test_dump_utc_converts_timezone_to_utc_iso_value() -> None:
    value = datetime(2026, 5, 8, 16, 30, tzinfo=timezone(timedelta(hours=8)))

    assert datetime_util.dump_utc(value) == '2026-05-08T08:30:00+00:00'


def test_parse_utc_rejects_naive_datetime_value() -> None:
    try:
        datetime_util.parse_utc('2026-05-08T08:30:00')
    except ValueError as exc:
        assert str(exc) == 'Datetime must include timezone.'
    else:
        raise AssertionError('Expected ValueError.')
