from app.api import BaseRouter
from app.api.v2.auth.auth import router as auth_router
from app.api.v2.auth.token import router as token_router

router = BaseRouter(prefix='/auth')
router.include_router(auth_router)
router.include_router(token_router)

__all__ = ['router']
