import httpx

from app.core.config import CONF
from app.infra.outbound_http import OutboundHttpTransport


def build_outbound_http_client(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    max_connections: int = 100,
    max_keepalive_connections: int = 20,
) -> httpx.AsyncClient:
    outbound_transport = transport or OutboundHttpTransport(
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive_connections,
    )
    return httpx.AsyncClient(
        transport=outbound_transport,
        follow_redirects=False,
        trust_env=False,
    )


def build_shared_http_client() -> httpx.AsyncClient:
    return build_outbound_http_client(
        max_connections=CONF.OUTBOUND_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=CONF.OUTBOUND_HTTP_MAX_KEEPALIVE,
    )


class SharedHttpClient:
    _client: httpx.AsyncClient | None = None

    @classmethod
    def set_client(cls, client: httpx.AsyncClient) -> None:
        cls._client = client

    @classmethod
    def get(cls) -> httpx.AsyncClient:
        if cls._client is None:
            raise RuntimeError('Shared HTTP client has not been set.')
        return cls._client

    @classmethod
    def clear(cls) -> None:
        cls._client = None
