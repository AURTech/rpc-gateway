from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastlog import configure, log
from starlette.responses import Response
from starlette.types import Scope

DOCUMENTATION_PATHS = (
    '/v2/openapi.json',
    '/docs',
    '/redoc',
    '/docs/oauth2-redirect',
)


async def documentation_not_found() -> None:
    raise HTTPException(status_code=404, detail='Not Found')


def custom_generate_unique_id(route: APIRoute) -> str:
    return f'{route.tags[0]}-{route.name}'


def _request_limit_error(scope: Scope, status_code: int, message: str) -> Response:
    from app.model.public import TronHttpApiFamily
    from app.model.transport import Transport
    from app.services.public import PublicGatewayAccessManager
    from app.services.public.http_api import TronHttpApiAdapter

    headers = {name.lower(): value for name, value in scope.get('headers', [])}
    host = headers.get(b'host', b'').decode('latin-1') or None
    if PublicGatewayAccessManager.match_host(host, Transport.HTTP_API) is None:
        from app.core.response import ErrorResponse

        return ErrorResponse(status_code=status_code, msg=message)
    path = scope.get('path', '')
    family = TronHttpApiFamily.V1 if '/v1/' in f'/{path.strip("/")}/' else TronHttpApiFamily.WALLET
    result = TronHttpApiAdapter.error(family, status_code, message)
    response = Response(content=result.body, status_code=result.status_code)
    response.raw_headers = [(name.encode('latin-1'), value.encode('latin-1')) for name, value in result.headers]
    return response


def init_app(lifespan_fn=None) -> FastAPI:
    # Runtime import: app package import must not create broker/router side effects before config is selected.
    from fastapi.middleware.cors import CORSMiddleware

    from app.api.router import router
    from app.core.config import CONF, validate_runtime_security
    from app.core.exception import register_exception_handlers
    from app.core.lifespan import lifespan
    from app.core.response import OrjsonResponse
    from app.core.trace import TRACE_ID_HEADER
    from app.middleware.client_context import ClientContextMiddleware
    from app.middleware.logging.request_log import RequestLogMiddleware
    from app.middleware.request_body_limit import RequestBodyLimitMiddleware
    from app.services.public.jsonrpc.manager import RPC_CACHE_HIT_HEADER

    validate_runtime_security(CONF)
    configure(level=CONF.log_level, log_path=CONF.LOG_PATH)

    openapi_url = '/v2/openapi.json' if CONF.is_dev else None
    docs_url = '/docs' if CONF.is_dev else None
    redoc_url = '/redoc' if CONF.is_dev else None
    swagger_ui_oauth2_redirect_url = '/docs/oauth2-redirect' if CONF.is_dev else None
    app = FastAPI(
        title=CONF.PROJECT_NAME,
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        swagger_ui_oauth2_redirect_url=swagger_ui_oauth2_redirect_url,
        default_response_class=OrjsonResponse,
        generate_unique_id_function=custom_generate_unique_id,
        lifespan=lifespan_fn or lifespan,
    )
    if CONF.is_dev:
        log.info(f'API documentation available at http://{CONF.HOST}:{CONF.PORT}/docs')

    app.add_middleware(
        # Reason: FastAPI accepts middleware classes at runtime; ty narrows this generic too much.
        CORSMiddleware,  # ty: ignore[invalid-argument-type]
        allow_origins=CONF.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=[TRACE_ID_HEADER, RPC_CACHE_HIT_HEADER, 'Idempotency-Replayed'],
    )

    app.add_middleware(
        # Reason: Starlette's type stub is narrower than its runtime middleware factory contract.
        RequestBodyLimitMiddleware,  # ty: ignore[invalid-argument-type]
        max_bytes=CONF.RPC_HTTP_MAX_REQUEST_BYTES,
        read_timeout_seconds=CONF.RPC_HTTP_BODY_READ_TIMEOUT_SECONDS,
        error_response_factory=_request_limit_error,
    )

    app.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        RequestLogMiddleware  # ty: ignore[invalid-argument-type]
    )
    app.add_middleware(
        # Reason: Starlette middleware classes are accepted by FastAPI at runtime.
        ClientContextMiddleware  # ty: ignore[invalid-argument-type]
    )
    register_exception_handlers(app)
    if not CONF.is_dev:
        for path in DOCUMENTATION_PATHS:
            app.add_api_route(
                path,
                documentation_not_found,
                include_in_schema=False,
                status_code=404,
                tags=['documentation'],
            )
    app.include_router(router)
    return app
