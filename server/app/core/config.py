import os
import re
from collections.abc import Mapping
from datetime import UTC
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, Self

from pydantic import AwareDatetime, Field, SecretBytes, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.origin import normalize_origin
from app.core.usage import (
    DEFAULT_USAGE_FINE_RETENTION_HOURS,
    DEFAULT_USAGE_RETENTION_MONTHS,
    DEFAULT_USAGE_STREAM_MAX_LENGTH,
    MAX_USAGE_FINE_RETENTION_HOURS,
    MAX_USAGE_RETENTION_MONTHS,
    MAX_USAGE_STREAM_LENGTH,
)
from app.model.admission import AdmissionBackend
from app.model.blockchain import Chain

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENDPOINT_MIN_MASTER_KEY_BYTES = 32

_ENDPOINT_KEY_VERSION_RE = re.compile(r'^[A-Za-z0-9._-]{1,32}$')

_SYSTEM_JSONRPC_CACHE_POSTGRES_RETENTION_SECONDS: Final[Mapping[Chain, int]] = MappingProxyType(
    {
        Chain.ETHEREUM: 7200,
        Chain.POLYGON: 1200,
        Chain.BSC: 600,
        Chain.ARBITRUM: 300,
        Chain.OPTIMISM: 1200,
        Chain.BASE: 1200,
        Chain.SOLANA: 1500,
        Chain.BITCOIN: 86_400,
        Chain.LITECOIN: 21_600,
        Chain.TRON: 1200,
    }
)
_SYSTEM_JSONRPC_CACHE_POSTGRES_CLEANUP_BATCH_BYTES: Final[int] = 32 * 1024 * 1024
_SYSTEM_JSONRPC_CACHE_POSTGRES_CLEANUP_MAX_BYTES: Final[int] = 1024 * 1024 * 1024


def normalize_endpoint_key_version(value: str) -> str:
    version = value.strip()
    if not _ENDPOINT_KEY_VERSION_RE.fullmatch(version):
        raise ValueError('Endpoint encryption key version is invalid.')
    return version


def normalize_endpoint_keyring(values: Mapping[str, str | SecretStr]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_version, raw_key in values.items():
        version = normalize_endpoint_key_version(raw_version)
        if version in normalized:
            raise ValueError('Endpoint encryption key versions must be unique after normalization.')
        key = raw_key.get_secret_value() if isinstance(raw_key, SecretStr) else raw_key
        key = key.strip()
        if not key:
            raise ValueError('Endpoint encryption key cannot be empty.')
        normalized[version] = key
    return normalized


_CONFIGURABLE_PRIVATE_NETWORKS: tuple[IPv4Network | IPv6Network, ...] = (
    ip_network('10.0.0.0/8'),
    ip_network('172.16.0.0/12'),
    ip_network('192.168.0.0/16'),
    ip_network('fc00::/7'),
)


def _is_configurable_private_network(network: IPv4Network | IPv6Network) -> bool:
    if isinstance(network, IPv4Network):
        return any(
            isinstance(private_network, IPv4Network) and network.subnet_of(private_network)
            for private_network in _CONFIGURABLE_PRIVATE_NETWORKS
        )
    return any(
        isinstance(private_network, IPv6Network) and network.subnet_of(private_network)
        for private_network in _CONFIGURABLE_PRIVATE_NETWORKS
    )


def _env_file_path() -> Path:
    env_file = Path(os.getenv('ENV_FILE', os.devnull).strip())
    return env_file if env_file.is_absolute() else PROJECT_ROOT / env_file


ENV_FILE = _env_file_path()


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        hide_input_in_errors=True,
    )

    # App
    APP_ENV: Literal['test', 'dev', 'prod'] = 'dev'
    PROJECT_NAME: str = 'rpc-gateway-api'

    # Runtime
    HOST: str = '127.0.0.1'
    PORT: int = 18173
    PUBLIC_RPC_API_BASE_URL: str = 'http://127.0.0.1:18173'
    PUBLIC_RPC_GATEWAY_BASE_DOMAIN: str = 'example.com'
    WORKERS: int = Field(default=1, ge=1)
    RELOAD: bool = False

    # Logging
    DEBUG: bool = False
    LOG_PATH: Path | None = None

    # Middleware
    CORS_ORIGINS: list[str] = ['http://127.0.0.1:19341', 'http://localhost:19341']
    RPC_HTTP_MAX_REQUEST_BYTES: int = Field(default=1024 * 1024, ge=1)
    RPC_HTTP_BODY_READ_TIMEOUT_SECONDS: int = Field(default=15, ge=1)
    JSONRPC_FORWARDING_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    HTTP_API_FORWARDING_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    RUNTIME_CIRCUIT_WINDOW_SECONDS: int = Field(default=30, ge=10, le=300)
    RUNTIME_CIRCUIT_WINDOW_BUCKET_SECONDS: int = Field(default=5, ge=1, le=60)
    RUNTIME_CIRCUIT_MIN_SAMPLES: int = Field(default=20, ge=5, le=100_000)
    RUNTIME_CIRCUIT_FAILURE_RATE: float = Field(default=0.5, gt=0, le=1)
    RUNTIME_CIRCUIT_HARD_FAILURE_THRESHOLD: int = Field(default=5, ge=3, le=100)
    RUNTIME_CIRCUIT_OPEN_SECONDS: int = Field(default=30, ge=1, le=300)
    RUNTIME_CIRCUIT_MAX_OPEN_SECONDS: int = Field(default=300, ge=1, le=3600)
    RUNTIME_CIRCUIT_RECOVERY_SUCCESSES: int = Field(default=2, ge=1, le=5)
    RUNTIME_CIRCUIT_PROBE_SECONDS: int = Field(default=30, ge=1, le=300)
    RUNTIME_CIRCUIT_THROTTLE_SECONDS: int = Field(default=2, ge=1, le=300)
    RUNTIME_CIRCUIT_THROTTLE_MAX_SECONDS: int = Field(default=30, ge=1, le=600)
    RUNTIME_CIRCUIT_TRACE_METHOD_PREFIXES: list[str] = ['debug_', 'trace_']
    PUBLIC_JSONRPC_RATE_LIMIT_BACKEND: AdmissionBackend = AdmissionBackend.REDIS
    PUBLIC_JSONRPC_RATE_LIMIT_POLICY_REFRESH_SECONDS: float = Field(default=5, ge=1, le=60)
    PUBLIC_JSONRPC_RATE_LIMIT_EXPECTED_REPLICAS: int = Field(default=1, ge=1, le=10_000)
    PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_MAX_PENDING: int = Field(default=4096, ge=1, le=65_536)
    PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_WORKERS: int = Field(default=16, ge=1, le=256)
    PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_REDIS_TIMEOUT_MS: int = Field(default=10, ge=1, le=1000)
    PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_SHUTDOWN_DRAIN_SECONDS: float = Field(default=1, ge=0, le=30)
    PUBLIC_HTTP_API_RATE_LIMIT_BACKEND: AdmissionBackend = AdmissionBackend.REDIS
    PUBLIC_HTTP_API_RATE_LIMIT_POLICY_REFRESH_SECONDS: float = Field(default=5, ge=1, le=60)
    PUBLIC_HTTP_API_RATE_LIMIT_EXPECTED_REPLICAS: int = Field(default=1, ge=1, le=10_000)
    PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_MAX_PENDING: int = Field(default=4096, ge=1, le=65_536)
    PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_WORKERS: int = Field(default=16, ge=1, le=256)
    PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_REDIS_TIMEOUT_MS: int = Field(default=10, ge=1, le=1000)
    PUBLIC_HTTP_API_RATE_LIMIT_SHADOW_SHUTDOWN_DRAIN_SECONDS: float = Field(default=1, ge=0, le=30)

    # System JSON-RPC Cache
    SYSTEM_JSONRPC_CACHE_ENABLED: bool = True
    SYSTEM_JSONRPC_CACHE_REDIS_TTL_MS: int = Field(default=250, ge=20, le=60_000)
    SYSTEM_JSONRPC_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN: dict[Chain, int] = Field(
        default_factory=lambda: dict(_SYSTEM_JSONRPC_CACHE_POSTGRES_RETENTION_SECONDS)
    )
    SYSTEM_JSONRPC_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES: int = Field(
        default=_SYSTEM_JSONRPC_CACHE_POSTGRES_CLEANUP_BATCH_BYTES,
        ge=1,
        le=_SYSTEM_JSONRPC_CACHE_POSTGRES_CLEANUP_MAX_BYTES,
    )

    # Database
    ORM_URL: str = 'postgres://rpc_gateway:rpc_gateway@127.0.0.1:5432/rpc_gateway'
    ORM_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=100)
    ORM_POOL_MAX_SIZE: int = Field(default=5, ge=1, le=100)
    SYSTEM_JSONRPC_CACHE_POSTGRES_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=100)
    SYSTEM_JSONRPC_CACHE_POSTGRES_POOL_MAX_SIZE: int = Field(default=8, ge=1, le=100)
    SYSTEM_JSONRPC_CACHE_COORDINATION_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=100)
    SYSTEM_JSONRPC_CACHE_COORDINATION_POOL_MAX_SIZE: int = Field(default=8, ge=1, le=100)

    # Redis
    REDIS_URL: str = 'redis://localhost:6379/0'
    REDIS_CONNECT_TIMEOUT_SECONDS: float = Field(default=1, gt=0, le=60)
    REDIS_SOCKET_TIMEOUT_SECONDS: float = Field(default=5, gt=0, le=60)

    # Usage
    USAGE_STREAM_MAX_LENGTH: int = Field(default=DEFAULT_USAGE_STREAM_MAX_LENGTH, ge=1, le=MAX_USAGE_STREAM_LENGTH)
    USAGE_HOURLY_RETENTION_MONTHS: int = Field(
        default=DEFAULT_USAGE_RETENTION_MONTHS,
        ge=2,
        le=MAX_USAGE_RETENTION_MONTHS,
    )
    USAGE_FINE_RETENTION_HOURS: int = Field(
        default=DEFAULT_USAGE_FINE_RETENTION_HOURS,
        ge=24,
        le=MAX_USAGE_FINE_RETENTION_HOURS,
    )
    USAGE_ASYNC_ROLLUP_CUTOVER_AT: AwareDatetime | None = None

    # TaskIQ
    TASKIQ_RETRY_COUNT: int = Field(default=3, ge=0)
    TASKIQ_RESULT_TTL_SECONDS: int = Field(default=3600, ge=1)
    TASKIQ_STREAM_MAXLEN: int = Field(default=100_000, ge=1)
    TASKIQ_UNACKNOWLEDGED_LOCK_TIMEOUT_SECONDS: int = Field(default=600, ge=1)

    # Tests
    TEST_ORM_URL: str = 'postgres://rpc_gateway:rpc_gateway_test@127.0.0.1:5432/rpc_gateway_test'
    TEST_REDIS_URL: str = 'redis://localhost:6379/15'

    # App API Keys
    APP_API_KEY_MASTER_KEY: SecretBytes = Field(min_length=32)

    # Runtime State
    RUNTIME_HEALTH_DISPATCHER_MAX_BATCHES: int = Field(default=4096, ge=1, le=100_000)
    RUNTIME_HEALTH_DISPATCHER_MAX_WAITERS: int = Field(default=2048, ge=1, le=100_000)
    RUNTIME_HEALTH_DISPATCHER_MAX_WAITERS_PER_BATCH: int = Field(default=64, ge=1, le=10_000)
    RUNTIME_HEALTH_DISPATCHER_RECORD_TIMEOUT_MS: int = Field(default=2000, ge=50, le=30_000)
    RUNTIME_HEALTH_DISPATCHER_COALESCE_MS: int = Field(default=5, ge=0, le=100)
    RUNTIME_HEALTH_DISPATCHER_SHUTDOWN_DRAIN_SECONDS: int = Field(default=5, ge=0, le=30)
    RUNTIME_TIP_DISPATCHER_MAX_ITEMS: int = Field(default=1024, ge=1, le=1024)
    RUNTIME_TIP_DISPATCHER_SHUTDOWN_DRAIN_SECONDS: int = Field(default=5, ge=0, le=30)
    ENDPOINT_HEALTH_CHECK_TIMEOUT_SECONDS: float = Field(default=5, gt=0, le=30)
    ENDPOINT_HEALTH_CHECK_MAX_RESPONSE_BYTES: int = Field(default=1024 * 1024, ge=1024, le=16 * 1024 * 1024)

    # Outbound network
    OUTBOUND_HTTP_MAX_CONNECTIONS: int = 100
    OUTBOUND_HTTP_MAX_KEEPALIVE: int = 50
    OUTBOUND_PRIVATE_NETWORK_CIDRS: list[str] = []

    # Auth
    GOOGLE_OAUTH_CLIENT_ID: str = ''
    GOOGLE_OAUTH_CLIENT_SECRET: str = ''
    GOOGLE_OAUTH_REDIRECT_URI: str = ''
    FRONTEND_AUTH_CALLBACK_URL: str = ''
    ADMIN_ALLOWED_EMAILS: list[str] = []
    AUTH_SESSION_SECRET: str = ''
    AUTH_PAT_HASH_SECRET: str = ''
    AUTH_COOKIE_SAMESITE: Literal['lax', 'strict', 'none'] = 'lax'
    AUTH_COOKIE_SECURE: bool | None = None
    AUTH_PASSWORD_MAX_CONCURRENCY: int = Field(default=4, ge=1, le=64)
    ENDPOINT_ACTIVE_KEY_VERSION: str = 'v1'
    ENDPOINT_KEYRING: dict[str, SecretStr] = Field(default_factory=dict)

    @field_validator('ENDPOINT_ACTIVE_KEY_VERSION')
    @classmethod
    def normalize_endpoint_key_version(cls, value: str) -> str:
        return normalize_endpoint_key_version(value)

    @field_validator('USAGE_ASYNC_ROLLUP_CUTOVER_AT')
    @classmethod
    def validate_usage_rollup_cutover(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        if value is None:
            return None
        normalized = value.astimezone(UTC)
        if normalized.minute or normalized.second or normalized.microsecond:
            raise ValueError('Usage rollup cutover must align to an exact UTC hour.')
        return normalized

    @field_validator('ENDPOINT_KEYRING')
    @classmethod
    def normalize_endpoint_keyring(cls, values: dict[str, SecretStr]) -> dict[str, SecretStr]:
        normalized = normalize_endpoint_keyring(values)
        return {version: SecretStr(key) for version, key in normalized.items()}

    @field_validator('OUTBOUND_PRIVATE_NETWORK_CIDRS')
    @classmethod
    def normalize_outbound_private_cidrs(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            try:
                network = ip_network(value.strip(), strict=False)
            except ValueError as exc:
                raise ValueError('OUTBOUND_PRIVATE_NETWORK_CIDRS must contain valid IPv4 or IPv6 networks.') from exc
            if not _is_configurable_private_network(network):
                raise ValueError('OUTBOUND_PRIVATE_NETWORK_CIDRS only accepts RFC 1918 or IPv6 unique-local networks.')
            cidr = network.with_prefixlen
            if cidr not in seen:
                normalized.append(cidr)
                seen.add(cidr)
        return normalized

    @field_validator('SYSTEM_JSONRPC_CACHE_POSTGRES_RETENTION_SECONDS_BY_CHAIN')
    @classmethod
    def validate_jsonrpc_cache_retention(cls, values: dict[Chain, int]) -> dict[Chain, int]:
        if set(values) != set(Chain):
            raise ValueError('System JSON-RPC Cache PostgreSQL retention must define every supported chain exactly once.')
        if any(isinstance(seconds, bool) or not 60 <= seconds <= 604_800 for seconds in values.values()):
            raise ValueError('System JSON-RPC Cache PostgreSQL retention must be between 60 seconds and 7 days.')
        return values

    @property
    def log_level(self) -> Literal['debug', 'info']:
        return 'debug' if self.DEBUG else 'info'

    @model_validator(mode='after')
    def validate_uvicorn_runtime(self) -> Self:
        if self.RELOAD and self.WORKERS > 1:
            raise ValueError('RELOAD=true only supports WORKERS=1. Set WORKERS=1 or disable RELOAD.')
        return self

    @model_validator(mode='after')
    def validate_database_runtime(self) -> Self:
        if not self.ORM_URL.startswith(('postgres://', 'postgresql://')):
            raise ValueError('ORM_URL must use postgres:// or postgresql://.')
        pool_sizes = (
            ('ORM', self.ORM_POOL_MIN_SIZE, self.ORM_POOL_MAX_SIZE),
            (
                'System JSON-RPC Cache PostgreSQL Retention',
                self.SYSTEM_JSONRPC_CACHE_POSTGRES_POOL_MIN_SIZE,
                self.SYSTEM_JSONRPC_CACHE_POSTGRES_POOL_MAX_SIZE,
            ),
            (
                'System JSON-RPC Cache Coordination',
                self.SYSTEM_JSONRPC_CACHE_COORDINATION_POOL_MIN_SIZE,
                self.SYSTEM_JSONRPC_CACHE_COORDINATION_POOL_MAX_SIZE,
            ),
        )
        for name, minimum, maximum in pool_sizes:
            if minimum > maximum:
                raise ValueError(f'{name} database pool minimum cannot exceed its maximum.')
        return self

    @model_validator(mode='after')
    def validate_health_limits(self) -> Self:
        if self.RUNTIME_HEALTH_DISPATCHER_MAX_WAITERS_PER_BATCH > self.RUNTIME_HEALTH_DISPATCHER_MAX_WAITERS:
            raise ValueError('Runtime Health per-batch waiter limit must not exceed the global waiter limit.')
        return self

    @model_validator(mode='after')
    def validate_circuit_policy(self) -> Self:
        if self.RUNTIME_CIRCUIT_WINDOW_SECONDS % self.RUNTIME_CIRCUIT_WINDOW_BUCKET_SECONDS:
            raise ValueError('Runtime Circuit window must be exactly divisible by its bucket duration.')
        if self.RUNTIME_CIRCUIT_MAX_OPEN_SECONDS < self.RUNTIME_CIRCUIT_OPEN_SECONDS:
            raise ValueError('Runtime Circuit maximum open time cannot be shorter than its initial open time.')
        if self.RUNTIME_CIRCUIT_THROTTLE_MAX_SECONDS < self.RUNTIME_CIRCUIT_THROTTLE_SECONDS:
            raise ValueError('Runtime Circuit throttle maximum cannot be shorter than its default.')
        prefixes = [prefix.strip() for prefix in self.RUNTIME_CIRCUIT_TRACE_METHOD_PREFIXES]
        if any(not prefix or len(prefix) > 64 for prefix in prefixes) or len(prefixes) != len(set(prefixes)):
            raise ValueError('Runtime Circuit trace method prefixes must be non-empty, unique, and at most 64 chars.')
        self.RUNTIME_CIRCUIT_TRACE_METHOD_PREFIXES = prefixes
        return self

    @model_validator(mode='after')
    def validate_security_runtime(self) -> Self:
        origins: list[str] = []
        seen: set[str] = set()
        for value in self.CORS_ORIGINS:
            if value.strip() == '*':
                raise ValueError('CORS_ORIGINS must not contain wildcard origins when credentials are enabled.')
            origin = normalize_origin(value)
            if origin not in seen:
                origins.append(origin)
                seen.add(origin)
        self.CORS_ORIGINS = origins

        endpoint_keyring = normalize_endpoint_keyring(self.ENDPOINT_KEYRING)
        if endpoint_keyring and self.ENDPOINT_ACTIVE_KEY_VERSION not in endpoint_keyring:
            raise ValueError('Endpoint active encryption key version is unavailable.')
        if self.APP_ENV == 'prod':
            if len(self.AUTH_SESSION_SECRET.strip().encode()) < 32:
                raise ValueError('AUTH_SESSION_SECRET must contain at least 32 bytes in production.')
            if len(self.AUTH_PAT_HASH_SECRET.strip().encode()) < 32:
                raise ValueError('AUTH_PAT_HASH_SECRET must contain at least 32 bytes in production.')
            if any(not origin.startswith('https://') for origin in origins):
                raise ValueError('CORS_ORIGINS must use https:// in production.')
            endpoint_active_key = endpoint_keyring.get(self.ENDPOINT_ACTIVE_KEY_VERSION)
            if not endpoint_active_key:
                raise ValueError('Endpoint encryption keyring must be configured in production.')
            if self.AUTH_COOKIE_SECURE is False:
                raise ValueError('AUTH_COOKIE_SECURE must not be false in production.')
            if self.LOG_PATH is not None and not self.LOG_PATH.is_absolute():
                raise ValueError('LOG_PATH must be absolute in production.')
        if self.AUTH_COOKIE_SAMESITE == 'none' and self.AUTH_COOKIE_SECURE is False:
            raise ValueError('AUTH_COOKIE_SECURE must not be false when AUTH_COOKIE_SAMESITE=none.')
        return self

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == 'dev'


def validate_runtime_security(conf: Config) -> None:
    """Reject encryption keys that are unsafe for a production process."""
    if conf.APP_ENV != 'prod':
        return
    endpoint_keyring = normalize_endpoint_keyring(conf.ENDPOINT_KEYRING)
    if not endpoint_keyring:
        raise ValueError('Endpoint encryption keyring must be configured in production.')
    endpoint_active_key = endpoint_keyring.get(conf.ENDPOINT_ACTIVE_KEY_VERSION)
    if endpoint_active_key is None:
        raise ValueError('Endpoint active encryption key version is unavailable.')
    if len(endpoint_active_key.encode()) < ENDPOINT_MIN_MASTER_KEY_BYTES:
        raise ValueError('Endpoint active encryption key must contain at least 32 bytes in production.')
    if any(len(key.encode()) < ENDPOINT_MIN_MASTER_KEY_BYTES for key in endpoint_keyring.values()):
        raise ValueError('Every endpoint encryption key must contain at least 32 bytes in production.')


@lru_cache
def get_conf() -> Config:
    # Reason: BaseSettings populates required fields from the selected environment at runtime.
    return Config()  # pyright: ignore[reportCallIssue]  # ty: ignore[missing-argument]


CONF = get_conf()
