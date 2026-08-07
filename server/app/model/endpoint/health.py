from datetime import datetime

from pydantic import BaseModel, Field

from app.model.runtime_state.endpoint.health import EndpointHealth, HealthFailure


class EndpointHealthCheck(BaseModel):
    endpoint_id: str = Field(min_length=1, max_length=64)
    checked_at: datetime
    success: bool
    limited: bool
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    failure: HealthFailure | None = None
    health: EndpointHealth
