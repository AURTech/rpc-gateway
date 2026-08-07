from app.model.overview import OverviewFleet
from app.orm.application import App
from app.orm.endpoint import Endpoint
from app.orm.provider import Provider


class OverviewQueryManager:
    @staticmethod
    async def get_fleet(account_id: str) -> OverviewFleet:
        endpoint_query = Endpoint.filter(account_id=account_id, deleted_at=None)
        endpoint_total = await endpoint_query.count()
        active_endpoint_total = await endpoint_query.filter(enabled=True).count()
        provider_total = await Provider.filter(account_id=account_id, deleted_at=None).count()
        app_total = await App.filter(account_id=account_id, deleted_at=None).count()
        return OverviewFleet(
            endpoint_total=endpoint_total,
            active_endpoint_total=active_endpoint_total,
            provider_total=provider_total,
            app_total=app_total,
        )
