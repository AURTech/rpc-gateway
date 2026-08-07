from dataclasses import dataclass
from enum import StrEnum


class AdmissionMode(StrEnum):
    DISABLED = 'disabled'
    SHADOW = 'shadow'
    ENFORCE = 'enforce'


class AdmissionBackend(StrEnum):
    REDIS = 'redis'
    LOCAL = 'local'


@dataclass(frozen=True, slots=True, kw_only=True)
class AdmissionRuntimePolicy:
    mode: AdmissionMode
    version: int
    redis_timeout_ms: int
    redis_admission_per_worker: int
    fallback_max_keys_per_worker: int
