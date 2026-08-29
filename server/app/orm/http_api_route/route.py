from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index

from app.model.http_api_route import HttpApiRetryPolicy, HttpApiRoutingStrategyType
from app.orm.endpoint import Endpoint
from app.orm.gateway import Gateway
from app.orm.mixin import GuidMixin, TimestampMixin


class HttpApiRoute(GuidMixin, TimestampMixin):
    gateway: fields.ForeignKeyRelation[Gateway] = fields.ForeignKeyField(
        'models.Gateway', related_name='http_api_routes', on_delete=OnDelete.CASCADE
    )
    gateway_id: str
    strategy_type = fields.CharEnumField(
        HttpApiRoutingStrategyType, default=HttpApiRoutingStrategyType.LOAD_BALANCE, max_length=32
    )
    max_attempts = fields.IntField(default=3)
    retry_policy = fields.CharEnumField(HttpApiRetryPolicy, default=HttpApiRetryPolicy.SAFE_ONLY, max_length=32)
    version = fields.IntField(default=1)

    class Meta:
        table = 'http_api_route'
        unique_together = (('gateway',),)
        indexes = (Index(fields=('gateway_id', 'deleted_at'), name='idx_http_api_route_gateway'),)


class HttpApiRouteTarget(GuidMixin, TimestampMixin):
    route: fields.ForeignKeyRelation[HttpApiRoute] = fields.ForeignKeyField(
        'models.HttpApiRoute', related_name='targets', on_delete=OnDelete.CASCADE
    )
    route_id: str
    endpoint: fields.ForeignKeyRelation[Endpoint] = fields.ForeignKeyField(
        'models.Endpoint', related_name='http_api_route_targets', on_delete=OnDelete.RESTRICT
    )
    endpoint_id: str
    source_provider = fields.ForeignKeyField(
        'models.Provider', related_name='http_api_route_targets', on_delete=OnDelete.SET_NULL, null=True
    )
    source_provider_id: str | None
    position = fields.IntField()
    weight = fields.IntField(null=True)

    class Meta:
        table = 'http_api_route_target'
        unique_together = (('route', 'endpoint'), ('route', 'position'))
        indexes = (
            Index(fields=('endpoint_id', 'deleted_at'), name='idx_http_api_route_target_endpoint'),
            Index(fields=('source_provider_id', 'deleted_at'), name='idx_http_api_route_target_provider'),
        )
