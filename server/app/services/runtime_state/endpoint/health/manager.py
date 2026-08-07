import asyncio
from collections.abc import Mapping

from redis.asyncio import Redis

from app.model.runtime_state.endpoint.health import EndpointHealth, HealthObservation
from app.services.runtime_state.endpoint.health.state import HealthBatch, make_batch
from app.services.runtime_state.endpoint.health.store import HealthStore


class HealthManager:
    def __init__(self, redis_client: Redis) -> None:
        self._store = HealthStore(redis_client)

    async def record(self, observation: HealthObservation) -> EndpointHealth:
        """Record one observation and update the shared window state."""
        return await self.record_batch(make_batch(observation))

    async def record_batch(self, batch: HealthBatch) -> EndpointHealth:
        """Record an already aggregated dispatcher batch exactly once."""
        return await self._store.record(batch)

    async def get(self, endpoint_id: str, endpoint_version: int) -> EndpointHealth | None:
        """Read the requested Endpoint version projected onto the live window."""
        return await self._store.get(endpoint_id, endpoint_version)

    async def get_many(self, endpoints: list[tuple[str, int]]) -> Mapping[str, EndpointHealth | None]:
        values = await asyncio.gather(*(self.get(endpoint_id, version) for endpoint_id, version in endpoints))
        return {endpoint_id: health for (endpoint_id, _version), health in zip(endpoints, values, strict=True)}
