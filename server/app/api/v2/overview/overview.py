from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.overview import OverviewFleet
from app.services.overview import OverviewQueryManager

router = BaseRouter(prefix='/overview', route_class=DashRouter)


@router.get('', response_model=OverviewFleet)
async def get_overview(account: AccountIdentityDep) -> OverviewFleet:
    return await OverviewQueryManager.get_fleet(account.id)
