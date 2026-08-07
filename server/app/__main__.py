import uvicorn

from app import init_app
from app.core.config import CONF

APP_IMPORT = 'app.__main__:app'
app = init_app()


def main() -> None:
    opts: dict = {
        'host': CONF.HOST,
        'port': CONF.PORT,
        'log_config': None,
        'access_log': False,
        'reload': CONF.RELOAD,
        'workers': CONF.WORKERS,
        'log_level': CONF.log_level,
    }
    uvicorn.run(APP_IMPORT, **opts)
