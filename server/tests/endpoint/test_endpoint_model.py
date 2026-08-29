from datetime import UTC, datetime

import pytest
from app.model.endpoint import (
    BulkDeleteEndpointParams,
    CreateEndpointParams,
    EndpointAuthType,
    EndpointPathAuthDetail,
    UpdateEndpointParams,
)
from app.orm.endpoint import Endpoint
from app.services.endpoint.crypto import encrypt_endpoint_secret, encrypt_endpoint_url
from app.services.endpoint.endpoint import EndpointManager
from pydantic import ValidationError


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('chain', 'ethereum'),
        ('network', 'mainnet'),
        ('protocol', 'jsonrpc'),
    ],
)
def test_update_endpoint_rejects_identity_fields(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        UpdateEndpointParams.model_validate({'expected_version': 1, 'name': 'Primary', field: value})

    assert exc_info.value.errors()[0]['type'] == 'extra_forbidden'


def test_update_endpoint_accepts_mutable_fields() -> None:
    params = UpdateEndpointParams.model_validate(
        {
            'expected_version': 2,
            'name': 'Primary',
            'url': 'https://rpc.example.com',
            'enabled': False,
        }
    )

    assert params.model_fields_set == {'expected_version', 'name', 'url', 'enabled'}


def test_bulk_delete_endpoint_params_reject_invalid_ids() -> None:
    with pytest.raises(ValidationError, match='at least 1 item'):
        BulkDeleteEndpointParams.model_validate({'endpoint_ids': []})

    with pytest.raises(ValidationError, match='cannot contain duplicates'):
        BulkDeleteEndpointParams.model_validate({'endpoint_ids': ['endpoint-1', 'endpoint-1']})

    with pytest.raises(ValidationError, match='at least 1 character'):
        BulkDeleteEndpointParams.model_validate({'endpoint_ids': ['']})

    with pytest.raises(ValidationError, match='at most 50 items'):
        BulkDeleteEndpointParams.model_validate({'endpoint_ids': [f'endpoint-{index}' for index in range(51)]})


def test_endpoint_detail_exposes_encrypted_path_credential() -> None:
    now = datetime.now(UTC)
    endpoint = Endpoint(
        id='endpoint-1',
        name='ethereum-mainnet',
        chain='ethereum',
        network='mainnet',
        protocol='jsonrpc',
        encrypted_url=encrypt_endpoint_url('https://rpc.example.com/{api_key}/solana-mainnet'),
        enabled=True,
        auth_type='path_api_key',
        auth_header_name=None,
        auth_query_param=None,
        encrypted_auth_secret=encrypt_endpoint_secret('path-secret'),
        version=1,
        created_at=now,
        modified_at=now,
    )
    endpoint.account_id = 'account-1'

    detail = EndpointManager.to_detail(endpoint)

    assert detail.url == 'https://rpc.example.com/{api_key}/solana-mainnet'
    assert isinstance(detail.auth, EndpointPathAuthDetail)
    assert detail.auth.secret == 'path-secret'


def test_endpoint_path_placeholder_requires_path_auth() -> None:
    with pytest.raises(ValidationError, match='requires path API key'):
        CreateEndpointParams.model_validate(
            {
                'name': 'solana-mainnet',
                'chain': 'solana',
                'network': 'mainnet-beta',
                'protocol': 'jsonrpc',
                'url': 'https://rpc.example.com/{api_key}/solana-mainnet',
            }
        )

    params = CreateEndpointParams.model_validate(
        {
            'name': 'solana-mainnet',
            'chain': 'solana',
            'network': 'mainnet-beta',
            'protocol': 'jsonrpc',
            'url': 'https://rpc.example.com/{api_key}/solana-mainnet',
            'auth': {'type': 'path_api_key', 'secret': 'path-secret'},
        }
    )
    assert params.auth.type is EndpointAuthType.PATH_API_KEY
