from tortoise import Model, fields
from tortoise.fields.base import OnDelete

from app.orm.endpoint.endpoint import Endpoint
from app.orm.provider.provider import Provider


class ProviderEndpointBinding(Model):
    endpoint: fields.OneToOneRelation[Endpoint] = fields.OneToOneField(
        'models.Endpoint',
        related_name='provider_binding',
        on_delete=OnDelete.CASCADE,
        primary_key=True,
    )
    endpoint_id: str
    provider: fields.ForeignKeyRelation[Provider] = fields.ForeignKeyField(
        'models.Provider',
        related_name='endpoint_bindings',
        on_delete=OnDelete.RESTRICT,
    )
    provider_id: str
    external_id = fields.CharField(max_length=512)
    last_seen_at = fields.DatetimeField()

    class Meta:
        table = 'provider_endpoint_binding'
        unique_together = (('provider', 'external_id'),)
