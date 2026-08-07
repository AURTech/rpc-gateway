from tortoise.backends.base.client import BaseDBAsyncClient

from app.orm.http_api_route import HttpApiRouteTarget
from app.services.jsonrpc_route.reference import DatabaseJsonRpcEndpointRouteReferenceLookup


class DatabaseEndpointRouteReferenceLookup:
    def __init__(self) -> None:
        self._jsonrpc = DatabaseJsonRpcEndpointRouteReferenceLookup()

    async def referenced_endpoint_ids(
        self,
        endpoint_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> set[str]:
        jsonrpc_ids = await self._jsonrpc.referenced_endpoint_ids(endpoint_ids, using_db=using_db)
        if not endpoint_ids:
            return jsonrpc_ids
        rows = await (
            HttpApiRouteTarget.filter(
                endpoint_id__in=endpoint_ids,
                deleted_at=None,
                route__deleted_at=None,
                route__gateway__deleted_at=None,
                route__gateway__app__deleted_at=None,
            )
            .using_db(using_db)
            .only('endpoint_id')
        )
        return jsonrpc_ids | {row.endpoint_id for row in rows}
