from fastlog import log

from app.core.errors import NotfoundError, UnavailableError
from app.model.endpoint import EndpointHealthCheck
from app.model.runtime_state.endpoint.health import HealthObservation, HealthOrigin
from app.orm.endpoint import Endpoint
from app.services.endpoint.probe import EndpointProbeManager
from app.services.runtime_state.endpoint.health import HealthDispatcher


class EndpointHealthCheckManager:
    def __init__(self, *, probe_manager: EndpointProbeManager, health_dispatcher: HealthDispatcher) -> None:
        self._probe_manager = probe_manager
        self._health_dispatcher = health_dispatcher

    async def check(self, account_id: str, endpoint_id: str) -> EndpointHealthCheck:
        """Run one fixed Endpoint probe and wait for its Runtime State observation.

        Disabled Endpoints remain checkable. Remote target and stored configuration failures are returned
        as probe results; an unavailable Runtime State write raises UnavailableError.
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
            health = await self._health_dispatcher.record(observation)
        except RuntimeError as exc:
            log.warning(f'Endpoint health observation unavailable | Account:{account_id} | Endpoint:{endpoint_id}')
            raise UnavailableError('Endpoint health state is unavailable.') from exc
        return EndpointHealthCheck(
            endpoint_id=endpoint.id,
            checked_at=probe.checked_at,
            success=probe.success,
            limited=probe.limited,
            latency_ms=probe.latency_ms,
            failure=probe.failure,
            health=health,
        )
