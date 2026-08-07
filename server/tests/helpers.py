from typing import Any

from httpx import ASGITransport, AsyncClient, Response
from starlette.types import ASGIApp


def asgi_client(app: ASGIApp, *, base_url: str = 'http://test') -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=base_url)


def assert_ok_response(response: Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {'msg', 'data'}
    assert data['msg'] == 'ok'
    return data
