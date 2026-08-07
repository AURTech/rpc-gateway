from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index

from app.model.endpoint import EndpointTrustLevel
from app.model.jsonrpc_route import JsonRpcRetryPolicy, JsonRpcRoutingStrategyType
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.mixin import GuidMixin, TimestampMixin


class JsonRpcRoute(GuidMixin, TimestampMixin):
    gateway: fields.ForeignKeyRelation[Gateway] = fields.ForeignKeyField(
        'models.Gateway',
        related_name='jsonrpc_routes',
        on_delete=OnDelete.CASCADE,
    )
    gateway_id: str
    strategy_type = fields.CharEnumField(
        JsonRpcRoutingStrategyType,
        default=JsonRpcRoutingStrategyType.LOAD_BALANCE,
        max_length=32,
    )
    minimum_trust = fields.CharEnumField(
        EndpointTrustLevel,
        default=EndpointTrustLevel.UNVERIFIED,
        max_length=32,
    )
    max_latency_ms = fields.FloatField(null=True)
    max_attempts = fields.IntField(default=3)
    retry_policy = fields.CharEnumField(JsonRpcRetryPolicy, default=JsonRpcRetryPolicy.SAFE_ONLY, max_length=32)
    version = fields.IntField(default=1)

    class Meta:
        table = 'jsonrpc_route'
        indexes = (Index(fields=('gateway_id', 'deleted_at', 'created_at'), name='idx_jsonrpc_route_gateway_created'),)


class JsonRpcRouteScope(GuidMixin, TimestampMixin):
    route: fields.ForeignKeyRelation[JsonRpcRoute] = fields.ForeignKeyField(
        'models.JsonRpcRoute',
        related_name='scopes',
        on_delete=OnDelete.CASCADE,
    )
    route_id: str
    gateway: fields.ForeignKeyRelation[Gateway] = fields.ForeignKeyField(
        'models.Gateway',
        related_name='jsonrpc_route_scopes',
        on_delete=OnDelete.CASCADE,
    )
    gateway_id: str
    method = fields.CharField(max_length=256)

    class Meta:
        table = 'jsonrpc_route_scope'
        unique_together = (('gateway', 'method'),)
        indexes = (Index(fields=('route_id', 'method'), name='idx_jsonrpc_route_scope_route_method'),)


class JsonRpcRouteTarget(GuidMixin, TimestampMixin):
    route: fields.ForeignKeyRelation[JsonRpcRoute] = fields.ForeignKeyField(
        'models.JsonRpcRoute',
        related_name='targets',
        on_delete=OnDelete.CASCADE,
    )
    route_id: str
    endpoint: fields.ForeignKeyRelation[Endpoint] = fields.ForeignKeyField(
        'models.Endpoint',
        related_name='jsonrpc_route_targets',
        on_delete=OnDelete.RESTRICT,
    )
    endpoint_id: str
    source_provider = fields.ForeignKeyField(
        'models.Provider',
        related_name='jsonrpc_route_targets',
        on_delete=OnDelete.SET_NULL,
        null=True,
    )
    source_provider_id: str | None
    position = fields.IntField()
    weight = fields.IntField(null=True)

    class Meta:
        table = 'jsonrpc_route_target'
        unique_together = (('route', 'endpoint'), ('route', 'position'))
        indexes = (
            Index(fields=('endpoint_id', 'deleted_at'), name='idx_jsonrpc_route_target_endpoint'),
            Index(fields=('source_provider_id', 'deleted_at'), name='idx_jsonrpc_route_target_provider'),
        )
