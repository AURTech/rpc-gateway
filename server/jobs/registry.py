from app.infra.broker import broker

from jobs.provider import provider
from jobs.system_cache import retention
from jobs.usage import usage

# Import task modules so their broker decorators register tasks for worker and scheduler entrypoints.
REGISTERED_JOB_MODULES = (retention, usage, provider)

__all__ = ('REGISTERED_JOB_MODULES', 'broker')
