from collections.abc import Mapping
from typing import Any

import orjson

from app.clients.provider.base import ProviderDiscoveryError
from app.clients.transport import HttpAuth, HttpTransport


async def get_json(
    transport: HttpTransport,
    url: str,
    *,
    query: Mapping[str, str | int | bool] | None = None,
    auth: HttpAuth | None = None,
) -> Any:
    response = await transport.request('GET', url, query=query, auth=auth, max_response_bytes=4 * 1024 * 1024)
    if not 200 <= response.status_code <= 299:
        raise ProviderDiscoveryError(f'Provider API returned status {response.status_code}.')
    try:
        return orjson.loads(response.body)
    except orjson.JSONDecodeError as exc:
        raise ProviderDiscoveryError('Provider API response is invalid.') from exc
