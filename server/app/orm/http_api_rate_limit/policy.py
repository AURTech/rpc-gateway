from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index

from app.model.admission import AdmissionMode
from app.orm.mixin import GuidMixin, TimestampMixin


class HttpApiRateLimitPolicy(GuidMixin, TimestampMixin):
    name = fields.CharField(max_length=64, unique=True)
    mode = fields.CharEnumField(AdmissionMode, max_length=16, default=AdmissionMode.SHADOW)
    max_inflight_per_worker = fields.IntField(default=64)
    redis_timeout_ms = fields.IntField(default=50)
    redis_admission_per_worker = fields.IntField(default=128)
    fallback_max_keys_per_worker = fields.IntField(default=50_000)
    global_rps = fields.IntField(default=500)
    global_burst = fields.IntField(default=1000)
    ip_rps = fields.IntField(default=100)
    ip_burst = fields.IntField(default=200)
    account_rps = fields.IntField(default=50)
    account_burst = fields.IntField(default=100)
    app_rps = fields.IntField(default=25)
    app_burst = fields.IntField(default=50)
    version = fields.IntField(default=1)
    modified_by_account_id = fields.CharField(max_length=21, null=True)

    class Meta:
        table = 'http_api_rate_limit_policy'
        indexes = (Index(fields=('deleted_at', 'name'), name='idx_http_api_rate_limit_policy_name'),)


class HttpApiRateLimitAuditEvent(GuidMixin, TimestampMixin):
    policy: fields.ForeignKeyRelation[HttpApiRateLimitPolicy] = fields.ForeignKeyField(
        'models.HttpApiRateLimitPolicy', related_name='audit_events', on_delete=OnDelete.CASCADE
    )
    policy_id: str
    actor_id = fields.CharField(max_length=21)
    actor_token_id = fields.CharField(max_length=21, null=True)
    previous_version = fields.IntField()
    new_version = fields.IntField()
    changed_fields = fields.JSONField(default=list)

    class Meta:
        table = 'http_api_rate_limit_policy_audit_event'
        indexes = (Index(fields=('policy_id', 'created_at'), name='idx_http_api_rate_limit_audit_policy'),)
