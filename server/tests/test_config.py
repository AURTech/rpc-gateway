from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from app.core.config import Config, validate_runtime_security
from app.infra.db import (
    DEFAULT_DB_CONNECTION,
    SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    SYSTEM_CACHE_RETENTION_DB_CONNECTION,
    create_tortoise_orm,
)
from app.model.admission import AdmissionBackend
from tortoise.config import DBUrlConfig

TEST_APP_KEY = 'a' * 32
TEST_ENDPOINT_KEY = 'e' * 32
TEST_PAT_KEY = 'p' * 32


def make_config(**values: object) -> Config:
    defaults: dict[str, object] = {
        'APP_ENV': 'test',
        'APP_API_KEY_MASTER_KEY': TEST_APP_KEY,
        'ENDPOINT_KEYRING': {'v1': TEST_ENDPOINT_KEY},
        'AUTH_PAT_HASH_SECRET': TEST_PAT_KEY,
    }
    defaults.update(values)
    # Reason: required settings are assembled dynamically by this test helper.
    return Config(**defaults)  # pyright: ignore[reportCallIssue, reportArgumentType]  # ty: ignore[invalid-argument-type]


def test_config_defaults_to_v2_control_plane_runtime() -> None:
    conf = make_config()
    assert conf.HOST == '127.0.0.1'
    assert conf.PORT == 18173
    assert conf.ENDPOINT_ACTIVE_KEY_VERSION == 'v1'
    assert 'v1' in conf.ENDPOINT_KEYRING
    assert conf.PUBLIC_JSONRPC_RATE_LIMIT_BACKEND is AdmissionBackend.REDIS
    assert conf.PUBLIC_HTTP_API_RATE_LIMIT_BACKEND is AdmissionBackend.REDIS
    assert conf.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_MAX_PENDING == 4096
    assert conf.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_WORKERS == 16
    assert conf.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_REDIS_TIMEOUT_MS == 10
    assert conf.PUBLIC_JSONRPC_RATE_LIMIT_SHADOW_SHUTDOWN_DRAIN_SECONDS == 1
    assert conf.SYSTEM_CACHE_ENABLED
    assert conf.SYSTEM_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES == 32 * 1024 * 1024
    assert conf.ORM_POOL_MAX_SIZE == 5
    assert conf.SYSTEM_CACHE_POSTGRES_POOL_MAX_SIZE == 8
    assert conf.SYSTEM_CACHE_COORDINATION_POOL_MAX_SIZE == 8


def test_admission_backends_are_configurable() -> None:
    conf = make_config(
        PUBLIC_JSONRPC_RATE_LIMIT_BACKEND='local',
        PUBLIC_HTTP_API_RATE_LIMIT_BACKEND='local',
    )

    assert conf.PUBLIC_JSONRPC_RATE_LIMIT_BACKEND is AdmissionBackend.LOCAL
    assert conf.PUBLIC_HTTP_API_RATE_LIMIT_BACKEND is AdmissionBackend.LOCAL


def test_system_cache_can_be_disabled() -> None:
    assert not make_config(SYSTEM_CACHE_ENABLED=False).SYSTEM_CACHE_ENABLED


def test_system_cache_cleanup_byte_limit_is_bounded() -> None:
    assert make_config(SYSTEM_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES=1024).SYSTEM_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES == 1024
    with pytest.raises(ValueError, match='greater than or equal to 1'):
        make_config(SYSTEM_CACHE_POSTGRES_CLEANUP_BATCH_MAX_BYTES=0)


def test_reload_rejects_multiple_workers() -> None:
    with pytest.raises(ValueError, match='RELOAD=true only supports WORKERS=1'):
        make_config(RELOAD=True, WORKERS=2)


def test_database_url_requires_postgresql() -> None:
    with pytest.raises(ValueError, match='ORM_URL must use postgres'):
        make_config(ORM_URL='sqlite://db.sqlite3')


@pytest.mark.parametrize(
    ('minimum_field', 'maximum_field'),
    [
        ('ORM_POOL_MIN_SIZE', 'ORM_POOL_MAX_SIZE'),
        ('SYSTEM_CACHE_POSTGRES_POOL_MIN_SIZE', 'SYSTEM_CACHE_POSTGRES_POOL_MAX_SIZE'),
        ('SYSTEM_CACHE_COORDINATION_POOL_MIN_SIZE', 'SYSTEM_CACHE_COORDINATION_POOL_MAX_SIZE'),
    ],
)
def test_database_pool_minimum_cannot_exceed_maximum(minimum_field: str, maximum_field: str) -> None:
    with pytest.raises(ValueError, match='minimum cannot exceed'):
        make_config(**{minimum_field: 3, maximum_field: 2})


def test_database_connections_have_independent_pool_capacity() -> None:
    config = create_tortoise_orm(
        make_config(
            ORM_POOL_MIN_SIZE=1,
            ORM_POOL_MAX_SIZE=5,
            SYSTEM_CACHE_POSTGRES_POOL_MIN_SIZE=2,
            SYSTEM_CACHE_POSTGRES_POOL_MAX_SIZE=7,
            SYSTEM_CACHE_COORDINATION_POOL_MIN_SIZE=3,
            SYSTEM_CACHE_COORDINATION_POOL_MAX_SIZE=6,
        )
    )

    expected = {
        DEFAULT_DB_CONNECTION: ('1', '5', 'rpc-gateway-api-business'),
        SYSTEM_CACHE_RETENTION_DB_CONNECTION: ('2', '7', 'rpc-gateway-api-cache-retention'),
        SYSTEM_CACHE_COORDINATION_DB_CONNECTION: ('3', '6', 'rpc-gateway-api-cache-coordination'),
    }
    for name, (minimum, maximum, application_name) in expected.items():
        connection = config.connections[name]
        assert isinstance(connection, DBUrlConfig)
        query = parse_qs(urlsplit(connection.url).query)
        assert query['minsize'] == [minimum]
        assert query['maxsize'] == [maximum]
        assert query['application_name'] == [application_name]


def test_private_network_cidrs_are_normalized() -> None:
    conf = make_config(OUTBOUND_PRIVATE_NETWORK_CIDRS=['10.20.1.1/16', '10.20.0.0/16', 'fd12:3456::1/48'])
    assert conf.OUTBOUND_PRIVATE_NETWORK_CIDRS == ['10.20.0.0/16', 'fd12:3456::/48']


@pytest.mark.parametrize('cidr', ['127.0.0.0/8', '169.254.0.0/16', '0.0.0.0/0', 'fe80::/10'])
def test_private_network_cidrs_reject_unsafe_ranges(cidr: str) -> None:
    with pytest.raises(ValueError, match='only accepts RFC 1918'):
        make_config(OUTBOUND_PRIVATE_NETWORK_CIDRS=[cidr])


def test_endpoint_keyring_normalizes_values() -> None:
    conf = make_config(ENDPOINT_ACTIVE_KEY_VERSION=' key-1 ', ENDPOINT_KEYRING={' key-1 ': f' {TEST_ENDPOINT_KEY} '})
    assert conf.ENDPOINT_ACTIVE_KEY_VERSION == 'key-1'
    assert conf.ENDPOINT_KEYRING['key-1'].get_secret_value() == TEST_ENDPOINT_KEY


def test_production_requires_endpoint_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('ENDPOINT_KEYRING', raising=False)
    with pytest.raises(ValueError, match='Endpoint encryption keyring must be configured'):
        make_config(
            APP_ENV='prod',
            AUTH_SESSION_SECRET='s' * 32,
            CORS_ORIGINS=['https://console.example.test'],
            ENDPOINT_KEYRING={},
        )


def test_production_requires_pat_hash_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('AUTH_PAT_HASH_SECRET', raising=False)
    with pytest.raises(ValueError, match='AUTH_PAT_HASH_SECRET must contain at least 32 bytes'):
        make_config(
            APP_ENV='prod',
            AUTH_SESSION_SECRET='s' * 32,
            AUTH_PAT_HASH_SECRET='',
            CORS_ORIGINS=['https://console.example.test'],
        )


def test_production_rejects_relative_log_path() -> None:
    with pytest.raises(ValueError, match='LOG_PATH must be absolute'):
        make_config(
            APP_ENV='prod',
            AUTH_SESSION_SECRET='s' * 32,
            CORS_ORIGINS=['https://console.example.test'],
            LOG_PATH=Path('logs/app.log'),
        )


def test_runtime_security_rejects_weak_endpoint_keys() -> None:
    conf = make_config(
        APP_ENV='prod',
        AUTH_SESSION_SECRET='s' * 32,
        CORS_ORIGINS=['https://console.example.test'],
        ENDPOINT_KEYRING={'v1': 'weak'},
    )
    with pytest.raises(ValueError, match='at least 32 bytes'):
        validate_runtime_security(conf)
