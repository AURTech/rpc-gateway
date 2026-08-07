import pytest
from app.core.errors import NotfoundError
from app.core.exception import register_exception_handlers
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from tests.helpers import asgi_client


class ValidationPayload(BaseModel):
    name: str


def test_api_error_uses_status_code_attribute() -> None:
    error = NotfoundError('missing')

    assert error.status_code == 404
    assert error.code == 'resource.not_found'


@pytest.mark.anyio
async def test_validation_error_returns_unified_format() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post('/validate')
    async def validate_payload(_payload: ValidationPayload) -> dict[str, str]:
        return {'msg': 'ok'}

    async with asgi_client(app) as client:
        response = await client.post('/validate', json={})

    assert response.status_code == 422
    data = response.json()
    assert set(data) == {'success', 'msg', 'code', 'details', 'trace_id'}
    assert data['success'] is False
    assert data['msg']
    assert data['code'] == 'request.validation'


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('GET', '/v2/nonexistent'),
        ('GET', '/not-a-path-key'),
    ],
)
async def test_not_found_returns_unified_format(client: AsyncClient, method: str, path: str) -> None:
    response = await client.request(method, path, json={'method': 'eth_blockNumber', 'id': 1})
    assert response.status_code == 404
    data = response.json()
    assert data == {
        'success': False,
        'msg': 'Not Found',
        'code': 'resource.not_found',
        'details': None,
        'trace_id': response.headers['A-Trace-ID'],
    }
