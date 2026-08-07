from typing import Any

from app.api import BaseRouter
from app.api.public import http_api, jsonrpc
from app.api.v2 import v2_router
from app.core.response import ErrorResponseModel, UnifiedResponse

responses: dict[int | str, dict[str, Any]] = {
    422: {'model': ErrorResponseModel},
}


router = BaseRouter(default_response_class=UnifiedResponse, responses=responses)
router.include_router(v2_router, prefix='/v2')
router.include_router(jsonrpc.router)
router.include_router(http_api.router)
