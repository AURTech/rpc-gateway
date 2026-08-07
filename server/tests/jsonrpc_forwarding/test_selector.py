from app.model.endpoint import EndpointTrustLevel
from app.model.runtime_state.endpoint.health import HealthStatus
from app.services.jsonrpc_forwarding.selector import select_candidates
from tests.jsonrpc_forwarding.factories import make_endpoint, make_health, make_plan


def test_select_candidates_keeps_unhealthy_as_soft_signal() -> None:
    endpoints = [
        make_endpoint('unhealthy'),
        make_endpoint('healthy'),
        make_endpoint('disabled', enabled=False),
        make_endpoint('untrusted', trust_level=EndpointTrustLevel.UNVERIFIED),
        make_endpoint('slow'),
        make_endpoint('unknown'),
    ]
    health_by_endpoint = {
        'unhealthy': make_health(HealthStatus.UNHEALTHY, 10),
        'healthy': make_health(HealthStatus.HEALTHY, 20),
        'disabled': make_health(HealthStatus.HEALTHY, 20),
        'untrusted': make_health(HealthStatus.HEALTHY, 20),
        'slow': make_health(HealthStatus.HEALTHY, 101),
    }

    plan = make_plan(endpoints, max_attempts=3, max_latency_ms=100)

    candidates = select_candidates(plan, health_by_endpoint)

    assert [candidate.target.endpoint.id for candidate in candidates] == ['unhealthy', 'healthy', 'unknown']
