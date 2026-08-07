from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil


def parse_retry_after_seconds(
    headers: Sequence[tuple[str, str]],
    *,
    now: datetime | None = None,
) -> int | None:
    """Parse one Retry-After delay without applying Circuit policy bounds."""
    raw = next((value.strip() for name, value in headers if name.lower() == 'retry-after'), '')
    if not raw:
        return None
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError('Retry-After reference time must include a timezone.')
    try:
        seconds = int(raw)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        seconds = ceil((parsed.astimezone(UTC) - current.astimezone(UTC)).total_seconds())
    return seconds if 1 <= seconds <= 3600 else None
