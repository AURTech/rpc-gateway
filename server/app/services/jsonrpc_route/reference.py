from tortoise.backends.base.client import BaseDBAsyncClient

from app.orm.jsonrpc_route import JsonRpcRouteTarget


class DatabaseJsonRpcEndpointRouteReferenceLookup:
    async def referenced_endpoint_ids(
        self,
        endpoint_ids: list[str],
        *,
        using_db: BaseDBAsyncClient,
    ) -> set[str]:
        if not endpoint_ids:
            return set()
        rows = await (
            JsonRpcRouteTarget.filter(
                endpoint_id__in=endpoint_ids,
                deleted_at=None,
                route__deleted_at=None,
                route__gateway__deleted_at=None,
                route__gateway__app__deleted_at=None,
            )
            .using_db(using_db)
            .only('endpoint_id')
        )
        return {row.endpoint_id for row in rows}
