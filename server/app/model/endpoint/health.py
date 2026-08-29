from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.model.runtime_state.endpoint.health import HealthStatus


class EndpointHealthItem(BaseModel):
    status: HealthStatus
    last_observed_at: datetime


class EndpointHealthCheck(BaseModel):
    status: Literal[HealthStatus.HEALTHY, HealthStatus.UNHEALTHY]
    last_observed_at: datetime
