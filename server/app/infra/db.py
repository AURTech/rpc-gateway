from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tortoise.backends.base.client import TransactionContext
from tortoise.config import AppConfig, DBUrlConfig, TortoiseConfig
from tortoise.context import get_current_context
from tortoise.transactions import in_transaction

from app.core.config import CONF, Config

DEFAULT_DB_CONNECTION = 'default'
SYSTEM_CACHE_RETENTION_DB_CONNECTION = 'system_cache_retention'
SYSTEM_CACHE_COORDINATION_DB_CONNECTION = 'system_cache_coordination'


def in_tx() -> TransactionContext:
    """Start a transaction on the active context's ordinary business connection group."""
    context = get_current_context()
    connection_name = context.default_connection if context and context.default_connection else DEFAULT_DB_CONNECTION
    return in_transaction(connection_name=connection_name)


def _pooled_url(url: str, *, minimum: int, maximum: int, application_name: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(minsize=str(minimum), maxsize=str(maximum), application_name=application_name)
    return urlunsplit(parts._replace(query=urlencode(query)))


def create_tortoise_orm(conf: Config) -> TortoiseConfig:
    return TortoiseConfig(
        connections={
            DEFAULT_DB_CONNECTION: DBUrlConfig(
                _pooled_url(
                    conf.ORM_URL,
                    minimum=conf.ORM_POOL_MIN_SIZE,
                    maximum=conf.ORM_POOL_MAX_SIZE,
                    application_name=f'{conf.PROJECT_NAME}-business',
                )
            ),
            SYSTEM_CACHE_RETENTION_DB_CONNECTION: DBUrlConfig(
                _pooled_url(
                    conf.ORM_URL,
                    minimum=conf.SYSTEM_CACHE_POSTGRES_POOL_MIN_SIZE,
                    maximum=conf.SYSTEM_CACHE_POSTGRES_POOL_MAX_SIZE,
                    application_name=f'{conf.PROJECT_NAME}-cache-retention',
                )
            ),
            SYSTEM_CACHE_COORDINATION_DB_CONNECTION: DBUrlConfig(
                _pooled_url(
                    conf.ORM_URL,
                    minimum=conf.SYSTEM_CACHE_COORDINATION_POOL_MIN_SIZE,
                    maximum=conf.SYSTEM_CACHE_COORDINATION_POOL_MAX_SIZE,
                    application_name=f'{conf.PROJECT_NAME}-cache-coordination',
                )
            ),
        },
        apps={
            'models': AppConfig(
                models=['app.orm'],
                default_connection=DEFAULT_DB_CONNECTION,
                migrations='migrations',
            ),
        },
    )


TORTOISE_ORM = create_tortoise_orm(CONF)
