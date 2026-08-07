from app.api import BaseRouter, DashRouter
from app.api.deps import AccountIdentityDep
from app.model.meta import RpcMethodCatalog, RpcMethodFamily
from app.services.meta import RpcMethodManager

router = BaseRouter(prefix='/meta', route_class=DashRouter)


@router.get('/jsonrpc-methods', response_model=RpcMethodCatalog)
async def list_jsonrpc_methods(
    account: AccountIdentityDep,
    protocol: RpcMethodFamily | None = None,
) -> RpcMethodCatalog:
    """Return the selectable JSON-RPC method catalog for dashboard routing forms."""
    return await RpcMethodManager.list_methods(protocol)
