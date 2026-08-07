from pydantic import BaseModel


class OverviewFleet(BaseModel):
    endpoint_total: int = 0
    active_endpoint_total: int = 0
    provider_total: int = 0
    app_total: int = 0
