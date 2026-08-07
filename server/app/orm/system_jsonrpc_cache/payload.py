from tortoise import fields, models
from tortoise.indexes import Index
from tortoise.migrations.constraints import CheckConstraint

from app.model.blockchain import Chain, Network


class SystemJsonRpcCachePayload(models.Model):
    id = fields.BigIntField(primary_key=True)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    method = fields.CharField(max_length=256)
    cache_key = fields.CharField(max_length=40)
    sequence = fields.BigIntField(null=True)
    payload = fields.BinaryField()
    payload_size = fields.IntField()
    stored_size = fields.IntField()
    fresh_until = fields.DatetimeField(null=True)
    stale_until = fields.DatetimeField(null=True)
    publisher_fence = fields.BigIntField(default=0)
    stored_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'system_jsonrpc_cache_payload'
        unique_together = (('chain', 'network', 'method', 'cache_key'),)
        constraints = (
            CheckConstraint(check='payload_size >= 0', name='chk_system_jsonrpc_cache_payload_size'),
            CheckConstraint(check='stored_size = octet_length(payload)', name='chk_system_jsonrpc_cache_stored_size'),
        )
        indexes = (Index(fields=('chain', 'stored_at'), name='idx_system_jsonrpc_cache_payload_retention'),)


class SystemJsonRpcCachePayloadLease(models.Model):
    id = fields.BigIntField(primary_key=True)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    method = fields.CharField(max_length=256)
    cache_key = fields.CharField(max_length=40)
    token = fields.CharField(max_length=64)
    fence = fields.BigIntField()
    lease_until = fields.DatetimeField()

    class Meta:
        table = 'system_jsonrpc_cache_payload_lease'
        unique_together = (('chain', 'network', 'method', 'cache_key'),)
        indexes = (Index(fields=('chain', 'lease_until'), name='idx_system_jsonrpc_cache_payload_lease_expiry'),)
