from datetime import UTC, datetime, timedelta


def now_utc() -> datetime:
    """Return the timezone-aware UTC datetime."""
    return datetime.now(UTC)


def next_utc_timestamp(previous: datetime | None) -> datetime:
    """Return a UTC timestamp strictly newer than an optional stored version."""
    now = now_utc()
    if previous is None:
        return now
    normalized = to_utc(previous)
    return now if now > normalized else normalized + timedelta(microseconds=1)


def floor_utc_hour(value: datetime) -> datetime:
    """Normalize a datetime to the containing UTC hour bucket."""
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def ceil_utc_hour(value: datetime) -> datetime:
    """Normalize a datetime to the next exclusive UTC hour bucket."""
    bucket = floor_utc_hour(value)
    if value.astimezone(UTC) == bucket:
        return bucket
    return bucket + timedelta(hours=1)


def floor_utc_five_minutes(value: datetime) -> datetime:
    """Normalize a datetime to the containing UTC five-minute bucket."""
    normalized = value.astimezone(UTC)
    minute = normalized.minute - normalized.minute % 5
    return normalized.replace(minute=minute, second=0, microsecond=0)


def ceil_utc_five_minutes(value: datetime) -> datetime:
    """Normalize a datetime to the next exclusive UTC five-minute bucket."""
    bucket = floor_utc_five_minutes(value)
    if value.astimezone(UTC) == bucket:
        return bucket
    return bucket + timedelta(minutes=5)


def to_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if value.tzinfo is None:
        raise ValueError('Datetime must include timezone.')
    return value.astimezone(UTC)


def dump_utc(value: datetime) -> str:
    """Serialize a timezone-aware datetime as UTC ISO 8601."""
    return to_utc(value).isoformat()


def parse_utc(value: str) -> datetime:
    """Parse an ISO 8601 datetime and normalize it to UTC."""
    return to_utc(datetime.fromisoformat(value))


def to_epoch_micros(value: datetime) -> int:
    """Return the epoch timestamp in whole microseconds."""
    return round(value.timestamp() * 1_000_000)


def to_epoch_millis(value: datetime) -> int:
    """Return the epoch timestamp in whole milliseconds."""
    return round(value.timestamp() * 1000)
