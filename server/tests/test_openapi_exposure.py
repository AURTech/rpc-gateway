import orjson
import pytest
from app import init_app
from app.core.config import CONF
from scripts.export_openapi import build_openapi
from tests.helpers import asgi_client

DOCUMENTATION_PATHS = (
    '/v2/openapi.json',
    '/docs',
    '/redoc',
    '/docs/oauth2-redirect',
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('app_env', 'expected_status'),
    [
        ('dev', 200),
        ('test', 404),
        ('prod', 404),
    ],
)
async def test_documentation_routes_depend_on_app_environment(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    expected_status: int,
) -> None:
    monkeypatch.setattr(CONF, 'APP_ENV', app_env)
    application = init_app()

    if app_env == 'dev':
        assert application.openapi_url == '/v2/openapi.json'
        assert application.docs_url == '/docs'
        assert application.redoc_url == '/redoc'
        assert application.swagger_ui_oauth2_redirect_url == '/docs/oauth2-redirect'
    else:
        assert application.openapi_url is None
        assert application.docs_url is None
        assert application.redoc_url is None
        assert application.swagger_ui_oauth2_redirect_url is None

    async with asgi_client(application) as client:
        for path in DOCUMENTATION_PATHS:
            response = await client.get(path)

            assert response.status_code == expected_status, response.text


def test_exported_management_contract_documents_pat_scopes_and_idempotency() -> None:
    schema = orjson.loads(build_openapi())
    schemes = schema['components']['securitySchemes']
    assert schemes['PersonalAccessToken'] == {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'PAT'}

    for operations in schema['paths'].values():
        for operation in operations.values():
            if not isinstance(operation, dict):
                continue
            security = operation.get('security', [])
            if any('PersonalAccessToken' in item for item in security):
                assert 'x-required-pat-scopes' in operation

    apps_post = schema['paths']['/v2/apps']['post']
    assert apps_post['x-required-pat-scopes'] == ['app-keys:write', 'apps:write']
    assert any(parameter['name'] == 'Idempotency-Key' for parameter in apps_post['parameters'])
    token_post = schema['paths']['/v2/auth/personal-access-tokens']['post']
    assert token_post['security'] == [{'SessionCookie': []}]
