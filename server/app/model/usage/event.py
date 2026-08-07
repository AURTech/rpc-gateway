from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.model.blockchain import Chain, Network, validate_chain_network


class GatewayUsageEvent(BaseModel):
    event_id: str = Field(min_length=32, max_length=64)
    account_id: str = Field(min_length=1, max_length=21)
    app_id: str = Field(min_length=1, max_length=21)
    gateway_id: str = Field(min_length=1, max_length=21)
    chain: Chain
    network: Network
    method: str = Field(min_length=1, max_length=256)
    started_at: AwareDatetime
    successful: bool
    duration_ms: int = Field(ge=0)
    request_bytes: int = Field(default=0, ge=0)
    response_bytes: int = Field(default=0, ge=0)
    cache_eligible: bool = False
    cache_hit: bool = False

    @model_validator(mode='after')
    def validate_cache_state(self) -> 'GatewayUsageEvent':
        validate_chain_network(self.chain, self.network)
        if self.cache_hit and not self.cache_eligible:
            raise ValueError('A cache hit must be cache eligible.')
        return self
