from datetime import UTC, datetime

import pytest
from app.model.blockchain import Chain, Network
from app.model.usage import GatewayUsageEvent
from pydantic import ValidationError


def test_usage_event_rejects_inconsistent_cache_state() -> None:
    with pytest.raises(ValidationError):
        GatewayUsageEvent(
            event_id='a' * 32,
            account_id='account-1',
            app_id='app-1',
            gateway_id='gateway-1',
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            method='eth_blockNumber',
            started_at=datetime.now(UTC),
            successful=True,
            duration_ms=1,
            cache_hit=True,
        )
