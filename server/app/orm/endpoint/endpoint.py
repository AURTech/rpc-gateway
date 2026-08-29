from collections.abc import Mapping
from datetime import datetime

from tortoise import fields
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index
from tortoise.migrations.constraints import CheckConstraint

from app.model.blockchain import Chain, Network
from app.model.endpoint import (
    EndpointAuditAction,
    EndpointAuthType,
    EndpointOriginType,
    EndpointProtocol,
)
from app.model.provider_state import ProviderEndpointSyncStatus
from app.orm.account.account import Account
from app.orm.mixin import GuidMixin, TimestampMixin

_AUTH_COLUMNS_CHECK = """
(
    auth_type = 'none'
    AND auth_header_name IS NULL
    AND auth_query_param IS NULL
    AND encrypted_auth_secret IS NULL
)
OR (
    auth_type IN ('bearer', 'path_api_key')
    AND auth_header_name IS NULL
    AND auth_query_param IS NULL
    AND encrypted_auth_secret IS NOT NULL
)
OR (
    auth_type = 'header_api_key'
    AND NULLIF(BTRIM(auth_header_name), '') IS NOT NULL
    AND auth_query_param IS NULL
    AND encrypted_auth_secret IS NOT NULL
)
OR (
    auth_type = 'query_api_key'
    AND auth_header_name IS NULL
    AND NULLIF(BTRIM(auth_query_param), '') IS NOT NULL
    AND encrypted_auth_secret IS NOT NULL
)
"""


class Endpoint(GuidMixin, TimestampMixin):
    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        'models.Account',
        related_name='endpoints',
        on_delete=OnDelete.CASCADE,
    )
    account_id: str
    name = fields.CharField(max_length=128)
    chain = fields.CharEnumField(Chain, max_length=32)
    network = fields.CharEnumField(Network, max_length=32)
    protocol = fields.CharEnumField(EndpointProtocol, max_length=32)
    encrypted_url = fields.TextField()
    enabled = fields.BooleanField(default=True)
    auth_type = fields.CharEnumField(EndpointAuthType, default=EndpointAuthType.NONE, max_length=32)
    auth_header_name = fields.CharField(max_length=128, null=True)
    auth_query_param = fields.CharField(max_length=128, null=True)
    encrypted_auth_secret = fields.TextField(null=True)
    version = fields.IntField(default=1)

    class Meta:
        table = 'endpoint'
        unique_together = (('account', 'name'),)
        constraints = (CheckConstraint(check=_AUTH_COLUMNS_CHECK, name='chk_endpoint_auth_columns'),)
        indexes = (
            Index(
                fields=('account_id', 'deleted_at', 'chain', 'network', 'protocol', 'enabled'),
                name='idx_endpoint_account_filters',
            ),
            Index(fields=('account_id', 'deleted_at', 'created_at'), name='idx_endpoint_account_order'),
        )

    def model_dump(
        self,
        *,
        provider: Mapping[str, object] | None = None,
        provider_external_id: str | None = None,
        provider_last_seen_at: datetime | None = None,
        provider_sync_status: ProviderEndpointSyncStatus | None = None,
    ) -> dict:
        provider_managed = provider is not None
        return {
            'id': self.id,
            'account_id': self.account_id,
            'name': self.name,
            'origin_type': EndpointOriginType.PROVIDER if provider_managed else EndpointOriginType.MANUAL,
            'provider': provider,
            'provider_external_id': provider_external_id if provider_managed else None,
            'provider_sync_status': (
                provider_sync_status or ProviderEndpointSyncStatus.AVAILABLE if provider_managed else None
            ),
            'provider_last_seen_at': provider_last_seen_at if provider_managed else None,
            'chain': Chain(self.chain),
            'network': Network(self.network),
            'protocol': EndpointProtocol(self.protocol),
            'enabled': self.enabled,
            'auth': self._auth_dump(),
            'version': self.version,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
        }

    def _auth_dump(self) -> dict[str, object]:
        auth_type = EndpointAuthType(self.auth_type)
        has_secret = bool(self.encrypted_auth_secret)
        if auth_type is EndpointAuthType.NONE:
            if self.auth_header_name is not None or self.auth_query_param is not None or has_secret:
                raise ValueError('Endpoint auth columns are invalid.')
            return {'type': auth_type, 'has_secret': False}
        if not has_secret:
            raise ValueError('Endpoint encrypted auth secret is unavailable.')
        if auth_type is EndpointAuthType.HEADER_API_KEY:
            if not self.auth_header_name or self.auth_query_param is not None:
                raise ValueError('Endpoint header auth columns are invalid.')
            return {'type': auth_type, 'header_name': self.auth_header_name, 'has_secret': True}
        if auth_type is EndpointAuthType.QUERY_API_KEY:
            if not self.auth_query_param or self.auth_header_name is not None:
                raise ValueError('Endpoint query auth columns are invalid.')
            return {'type': auth_type, 'query_param': self.auth_query_param, 'has_secret': True}
        if self.auth_header_name is not None or self.auth_query_param is not None:
            raise ValueError('Endpoint auth columns are invalid.')
        return {'type': auth_type, 'has_secret': True}


class EndpointAuditEvent(GuidMixin):
    endpoint: fields.ForeignKeyRelation[Endpoint] = fields.ForeignKeyField(
        'models.Endpoint',
        related_name='audit_events',
        on_delete=OnDelete.CASCADE,
    )
    endpoint_id: str
    account_id = fields.CharField(max_length=21)
    actor_id = fields.CharField(max_length=21)
    actor_token_id = fields.CharField(max_length=21, null=True)
    action = fields.CharEnumField(EndpointAuditAction, max_length=32)
    previous_version = fields.IntField(null=True)
    new_version = fields.IntField()
    changed_fields = fields.JSONField(default=list)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'endpoint_audit_event'
        indexes = (
            Index(fields=('endpoint_id', 'account_id', 'created_at'), name='idx_endpoint_audit_endpoint_order'),
            Index(fields=('account_id', 'created_at'), name='idx_endpoint_audit_account_order'),
        )

    def model_dump(self) -> dict:
        fields_value = self.changed_fields if isinstance(self.changed_fields, list) else []
        changed_fields = [value for value in fields_value if isinstance(value, str)]
        return {
            'id': self.id,
            'endpoint_id': self.endpoint_id,
            'account_id': self.account_id,
            'actor_id': self.actor_id,
            'actor_token_id': self.actor_token_id,
            'action': EndpointAuditAction(self.action),
            'previous_version': self.previous_version,
            'new_version': self.new_version,
            'changed_fields': changed_fields,
            'created_at': self.created_at,
        }
