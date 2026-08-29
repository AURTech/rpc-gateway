from datetime import UTC, datetime

import pytest
from app.core.config import CONF
from app.model.blockchain import Chain, Network
from app.model.provider import CreateProviderParams, ProviderNetworkPair, UpdateProviderParams
from app.model.provider.capability import provider_transports
from app.model.provider_state import ProviderVendor
from app.model.transport import Transport
from app.orm.provider import Provider
from app.services.endpoint.crypto import (
    decrypt_endpoint_secret,
)
from app.services.provider.crypto import (
    ProviderCredentialConfigError,
    decrypt_provider_credential,
    encrypt_provider_credential,
    provider_cipher_info,
)
from app.services.provider.provider import ProviderManager
from pydantic import SecretStr, ValidationError


def test_provider_params_normalize_credentials_and_networks() -> None:
    params = CreateProviderParams.model_validate(
        {
            'name': '  primary  ',
            'vendor': 'alchemy',
            'credential': {'secret': '  secret  '},
            'networks': [
                {'chain': 'ethereum', 'network': 'mainnet'},
                {'chain': 'ethereum', 'network': 'mainnet'},
            ],
        }
    )
    assert params.name == 'primary'
    assert params.credential.secret.get_secret_value() == 'secret'
    assert params.networks is not None
    assert len(params.networks) == 1


def test_provider_params_reject_error_text_as_credential() -> None:
    with pytest.raises(ValueError, match='cannot contain whitespace'):
        CreateProviderParams.model_validate(
            {
                'name': 'alchemy-main',
                'vendor': 'alchemy',
                'credential': {'secret': 'Provider name already exists.'},
            }
        )


def test_provider_params_validate_vendor_network_capabilities() -> None:
    solana = ProviderNetworkPair.model_validate({'chain': 'solana', 'network': 'mainnet-beta'})
    assert solana.chain == 'solana'
    CreateProviderParams.model_validate(
        {
            'name': 'alchemy',
            'vendor': 'alchemy',
            'credential': {'secret': 'secret'},
            'networks': [solana],
        }
    )
    with pytest.raises(ValidationError, match='does not support'):
        CreateProviderParams.model_validate(
            {
                'name': 'drpc',
                'vendor': 'drpc',
                'credential': {'secret': 'secret'},
                'networks': [{'chain': 'bitcoin', 'network': 'testnet'}],
            }
        )


def test_provider_capabilities_define_vendor_specific_transports() -> None:
    assert provider_transports(ProviderVendor.ALCHEMY, Chain.TRON, Network.MAINNET) == frozenset(
        {Transport.JSONRPC, Transport.HTTP_API}
    )
    assert provider_transports(ProviderVendor.DRPC, Chain.TRON, Network.MAINNET) == frozenset({Transport.JSONRPC})
    assert provider_transports(ProviderVendor.DRPC, Chain.TRON, Network.NILE) == frozenset()
    with pytest.raises(ValidationError, match='does not support'):
        CreateProviderParams.model_validate(
            {
                'name': 'tenderly',
                'vendor': 'tenderly',
                'credential': {'secret': 'secret'},
                'networks': [{'chain': 'bsc', 'network': 'mainnet'}],
            }
        )


def test_provider_update_requires_version_and_a_change() -> None:
    with pytest.raises(ValidationError, match='At least one'):
        UpdateProviderParams(expected_version=1)
    params = UpdateProviderParams(expected_version=2, enabled=False)
    assert params.expected_version == 2
    assert params.enabled is False


def test_provider_update_allows_unrelated_changes_with_configured_networks() -> None:
    now = datetime.now(UTC)
    provider = Provider(
        id='provider-1',
        name='tenderly',
        vendor='tenderly',
        enabled=True,
        sync_enabled=False,
        next_sync_at=None,
        encrypted_credential=encrypt_provider_credential('provider-secret'),
        settings={},
        networks=[{'chain': 'bsc', 'network': 'mainnet'}],
        last_sync_at=None,
        last_sync_status='never',
        version=1,
        created_at=now,
        modified_at=now,
    )
    provider.account_id = 'account-1'

    values = ProviderManager._update_values(provider, UpdateProviderParams(expected_version=1, enabled=False))

    assert values == {'enabled': False, 'next_sync_at': None}


def test_provider_credentials_use_an_independent_endpoint_key_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CONF, 'ENDPOINT_ACTIVE_KEY_VERSION', 'v1')
    monkeypatch.setattr(CONF, 'ENDPOINT_KEYRING', {'v1': SecretStr('provider-test-master-key-material-32-bytes')})

    encrypted = encrypt_provider_credential('provider-secret')

    assert decrypt_provider_credential(encrypted) == 'provider-secret'
    info = provider_cipher_info(encrypted)
    assert info is not None
    assert info.purpose == 'provider'
    with pytest.raises(ProviderCredentialConfigError):
        decrypt_endpoint_secret(encrypted)
