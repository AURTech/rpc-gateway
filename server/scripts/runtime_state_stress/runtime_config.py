import math
from typing import Final

from app.core.config import CONF
from app.services.runtime_state.chain.tip.store import LEASE_TIMEOUT_FACTOR

REDIS_IO_MS: Final[int] = max(1, math.ceil(CONF.REDIS_SOCKET_TIMEOUT_SECONDS * 1000))
RENEW_THRESHOLD_SECONDS: Final[float] = REDIS_IO_MS / 1000
LEASE_SECONDS: Final[float] = REDIS_IO_MS * LEASE_TIMEOUT_FACTOR / 1000
