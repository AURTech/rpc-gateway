from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.infra.db import (
    DEFAULT_DB_CONNECTION,
    SYSTEM_CACHE_COORDINATION_DB_CONNECTION,
    SYSTEM_CACHE_RETENTION_DB_CONNECTION,
)

STRESS_DB_POOL_MAX_SIZE = 2


def stress_database_connections(schema_url: str) -> dict[str, str]:
    connections: dict[str, str] = {}
    application_names = {
        DEFAULT_DB_CONNECTION: 'system-cache-stress-business',
        SYSTEM_CACHE_RETENTION_DB_CONNECTION: 'system-cache-stress-retention',
        SYSTEM_CACHE_COORDINATION_DB_CONNECTION: 'system-cache-stress-coordination',
    }
    for connection_name, application_name in application_names.items():
        parsed = urlsplit(schema_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update(minsize='1', maxsize=str(STRESS_DB_POOL_MAX_SIZE), application_name=application_name)
        connections[connection_name] = urlunsplit(parsed._replace(query=urlencode(query)))
    return connections
