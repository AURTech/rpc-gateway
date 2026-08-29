from fastlog import log
from redis.exceptions import RedisError

from app.core.errors import NotfoundError, UnavailableError
from app.model.endpoint import EndpointHealthCheck, EndpointHealthItem, EndpointItem, EndpointList
from app.model.runtime_state.endpoint.health import EndpointHealth, HealthObservation, HealthOrigin, HealthStatus
from app.orm.endpoint import Endpoint
from app.services.endpoint.probe import EndpointProbeManager
from app.services.runtime_state.endpoint.health import HealthManager


class EndpointHealthManager:
    def __init__(self, *, probe_manager: EndpointProbeManager, health_manager: HealthManager) -> None:
        self._probe_manager = probe_manager
        self._health_manager = health_manager

    async def check(self, account_id: str, endpoint_id: str) -> EndpointHealthCheck:
        """Run one fixed Endpoint probe and write its result to the shared Runtime State.

        Disabled Endpoints remain checkable. Probe failures set the Endpoint unhealthy; an unavailable
        Runtime State write raises UnavailableError.
        """
        endpoint = await Endpoint.filter(id=endpoint_id, account_id=account_id, deleted_at=None).first()
        if endpoint is None:
            raise NotfoundError('Endpoint not found.')
        probe = await self._probe_manager.probe(endpoint)
        observation = HealthObservation(
            endpoint_id=endpoint.id,
            endpoint_version=endpoint.version,
            origin=HealthOrigin.MANUAL,
            success=probe.success,
            failure=probe.failure,
            latency_ms=probe.latency_ms,
            observed_at=probe.checked_at,
        )
        try:
            health = await self._health_manager.record(observation)
        except (RedisError, RuntimeError) as exc:
            log.warning(f'Endpoint health observation unavailable | Account:{account_id} | Endpoint:{endpoint_id}')
            raise UnavailableError('Endpoint health state is unavailable.') from exc
        status = HealthStatus.HEALTHY if probe.success else HealthStatus.UNHEALTHY
        return EndpointHealthCheck(status=status, last_observed_at=health.last_observed_at)

    async def add_list_health(self, value: EndpointList) -> EndpointList:
        """Add fail-soft Runtime State snapshots to one Endpoint page."""
        endpoints = [(endpoint.id, endpoint.version) for endpoint in value.items]
        try:
            health_by_endpoint = await self._health_manager.get_many(endpoints)
        except (RedisError, RuntimeError):
            log.warning('Endpoint health snapshots unavailable for registry list')
            return value
        items: list[EndpointItem] = []
        for endpoint in value.items:
            health = health_by_endpoint.get(endpoint.id)
            if health is None:
                items.append(endpoint)
                continue
            item = EndpointHealthManager._to_item(health)
            items.append(endpoint.model_copy(update={'health': item}))
        return value.model_copy(update={'items': items})

    async def add_item_health[T: EndpointItem](self, value: T) -> T:
        """Add a fail-soft Runtime State snapshot to one Endpoint response."""
        try:
            health = await self._health_manager.get(value.id, value.version)
        except (RedisError, RuntimeError):
            log.warning(f'Endpoint health snapshot unavailable | Endpoint:{value.id}')
            return value
        if health is None:
            return value
        return value.model_copy(update={'health': EndpointHealthManager._to_item(health)})

    @staticmethod
    def _to_item(health: EndpointHealth) -> EndpointHealthItem:
        return EndpointHealthItem(
            status=health.status,
            last_observed_at=health.last_observed_at,
        )
