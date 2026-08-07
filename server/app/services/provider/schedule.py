from datetime import UTC, datetime, timedelta
from hashlib import sha256

PROVIDER_SYNC_WINDOW_MINUTES = 15
PROVIDER_SYNC_SLOTS_PER_DAY = 24 * 60 // PROVIDER_SYNC_WINDOW_MINUTES


def provider_sync_window_start(value: datetime) -> datetime:
    normalized = value.astimezone(UTC)
    minute = normalized.minute - normalized.minute % PROVIDER_SYNC_WINDOW_MINUTES
    return normalized.replace(minute=minute, second=0, microsecond=0)


def _provider_sync_slot(account_id: str) -> int:
    slot_hash = sha256(account_id.encode()).hexdigest()
    return int(slot_hash[:4], 16) % PROVIDER_SYNC_SLOTS_PER_DAY


def next_provider_sync_at(account_id: str, *, after: datetime) -> datetime:
    normalized = after.astimezone(UTC)
    day_start = normalized.replace(hour=0, minute=0, second=0, microsecond=0)
    scheduled_at = day_start + timedelta(minutes=_provider_sync_slot(account_id) * PROVIDER_SYNC_WINDOW_MINUTES)
    if scheduled_at <= normalized:
        scheduled_at += timedelta(days=1)
    return scheduled_at


def next_day_sync_at(account_id: str, *, after: datetime) -> datetime:
    normalized = after.astimezone(UTC)
    day_start = normalized.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return day_start + timedelta(minutes=_provider_sync_slot(account_id) * PROVIDER_SYNC_WINDOW_MINUTES)
