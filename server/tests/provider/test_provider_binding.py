from datetime import UTC, datetime

from app.orm.endpoint import Endpoint
from app.orm.provider import ProviderEndpointBinding


def _endpoint(*, deleted_at: datetime | None = None) -> Endpoint:
    now = datetime.now(UTC)
    endpoint = Endpoint(
        id='endpoint-1',
        name='ethereum-mainnet',
        chain='ethereum',
        network='mainnet',
        protocol='jsonrpc',
        encrypted_url='encrypted-url',
        enabled=True,
        auth_type='none',
        auth_header_name=None,
        auth_query_param=None,
        encrypted_auth_secret=None,
        version=1,
        created_at=now,
        modified_at=now,
        deleted_at=deleted_at,
    )
    endpoint.account_id = 'account-1'
    return endpoint


def test_endpoint_provider_state_is_normalized_into_binding() -> None:
    endpoint_fields = Endpoint._meta.fields_map

    assert 'origin_type' not in endpoint_fields
    assert 'provider_id' not in endpoint_fields
    assert 'provider_external_id' not in endpoint_fields
    assert 'provider_sync_status' not in endpoint_fields
    assert 'provider_last_seen_at' not in endpoint_fields
    assert ProviderEndpointBinding._meta.db_table == 'provider_endpoint_binding'
    assert ProviderEndpointBinding._meta.unique_together == (('provider', 'external_id'),)


def test_endpoint_provider_response_fields_are_derived() -> None:
    last_seen_at = datetime.now(UTC)
    provider = {'id': 'provider-1', 'name': 'Alchemy', 'vendor': 'alchemy', 'vendor_label': 'Alchemy'}

    manual = _endpoint().model_dump()
    available = _endpoint().model_dump(
        provider=provider,
        provider_external_id='alchemy:1',
        provider_last_seen_at=last_seen_at,
    )
    missing = _endpoint(deleted_at=datetime.now(UTC)).model_dump(
        provider=provider,
        provider_external_id='alchemy:1',
        provider_last_seen_at=last_seen_at,
    )

    assert manual['origin_type'] == 'manual'
    assert manual['provider_sync_status'] is None
    assert available['origin_type'] == 'provider'
    assert available['provider_sync_status'] == 'available'
    assert available['provider_external_id'] == 'alchemy:1'
    assert missing['provider_sync_status'] == 'available'
