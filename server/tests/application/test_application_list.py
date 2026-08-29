from datetime import UTC, datetime

from app.model.blockchain import Chain, Network
from app.orm.application import App
from app.orm.gateway import Gateway
from app.services.application.application import ApplicationManager


def _gateway(chain: Chain, network: Network, *, enabled: bool) -> Gateway:
    return Gateway(
        app_id='app-1',
        name=f'{chain.value}-{network.value}',
        chain=chain,
        network=network,
        transport_types=['jsonrpc'],
        enabled=enabled,
    )


def test_app_list_item_chains_cover_enabled_gateways_only() -> None:
    now = datetime.now(UTC)
    app = App(id='app-1', name='List app', enabled=True, version=1, created_at=now, modified_at=now)
    app.provider_id = None
    gateways = [
        _gateway(Chain.ETHEREUM, Network.MAINNET, enabled=True),
        _gateway(Chain.TRON, Network.MAINNET, enabled=False),
        _gateway(Chain.SOLANA, Network.MAINNET_BETA, enabled=True),
    ]

    item = ApplicationManager._to_list_item(app, gateways)

    assert item.chains == [Chain.ETHEREUM, Chain.SOLANA]
    assert item.gateway_count == 3
    assert item.enabled_gateway_count == 2
