from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index

from app.model.blockchain import Chain, Network
from app.orm.application import App
from app.orm.mixin import GuidMixin, TimestampMixin


class Gateway(GuidMixin, TimestampMixin):
    app: fields.ForeignKeyRelation[App] = fields.ForeignKeyField(
        'models.App',
        related_name='gateways',
        on_delete=OnDelete.CASCADE,
    )
    app_id: str
    name = fields.CharField(max_length=128)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    transport_types = fields.JSONField()
    enabled = fields.BooleanField(default=True)
    version = fields.IntField(default=1)

    class Meta:
        table = 'gateway'
        unique_together = (('app', 'chain', 'network'),)
        indexes = (
            Index(fields=('app_id', 'deleted_at', 'created_at'), name='idx_gateway_app_created'),
            Index(fields=('app_id', 'deleted_at', 'enabled'), name='idx_gateway_app_enabled'),
            Index(fields=('deleted_at', 'chain', 'network', 'enabled'), name='idx_gateway_chain_network'),
        )
