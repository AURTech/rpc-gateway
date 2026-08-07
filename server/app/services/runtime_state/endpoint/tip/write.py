from enum import StrEnum


class TipWriteResult(StrEnum):
    STORED = 'stored'
    STALE_NOOP = 'stale_noop'
    CAPACITY_REJECTED = 'capacity_rejected'
    FUTURE_REJECTED = 'future_rejected'
