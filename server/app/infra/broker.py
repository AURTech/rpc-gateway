from taskiq import AsyncBroker, SimpleRetryMiddleware
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.config import CONF
from app.infra.task_trace import TraceMiddleware

broker: AsyncBroker

broker = (
    RedisStreamBroker(
        url=CONF.REDIS_URL,
        queue_name=CONF.PROJECT_NAME,
        maxlen=CONF.TASKIQ_STREAM_MAXLEN,
        unacknowledged_lock_timeout=CONF.TASKIQ_UNACKNOWLEDGED_LOCK_TIMEOUT_SECONDS,
        socket_connect_timeout=CONF.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=CONF.REDIS_SOCKET_TIMEOUT_SECONDS,
        retry_on_timeout=False,
    )
    .with_result_backend(
        RedisAsyncResultBackend(
            redis_url=CONF.REDIS_URL,
            result_ex_time=CONF.TASKIQ_RESULT_TTL_SECONDS,
            prefix_str=CONF.PROJECT_NAME,
            socket_connect_timeout=CONF.REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=CONF.REDIS_SOCKET_TIMEOUT_SECONDS,
            retry_on_timeout=False,
        )
    )
    .with_middlewares(TraceMiddleware(), SimpleRetryMiddleware(default_retry_count=CONF.TASKIQ_RETRY_COUNT))
)
