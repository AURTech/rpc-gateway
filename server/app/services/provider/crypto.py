from app.core.resource_secret import (
    ResourceCipherInfo,
    ResourceSecretConfigError,
    decrypt_resource_secret,
    encrypt_resource_secret,
    rekey_resource_secret,
    resource_cipher_info,
)

ProviderCredentialConfigError = ResourceSecretConfigError


def encrypt_provider_credential(secret: str) -> str:
    value = secret.strip()
    if not value:
        raise ValueError('Provider credential cannot be empty.')
    return encrypt_resource_secret(value, purpose='provider')


def decrypt_provider_credential(encrypted_credential: str) -> str:
    value = encrypted_credential.strip()
    if not value:
        raise ProviderCredentialConfigError('Provider credential is unavailable.')
    return decrypt_resource_secret(value, purpose='provider')


def rekey_provider_credential(encrypted_credential: str) -> str:
    return rekey_resource_secret(encrypted_credential, purpose='provider')


def provider_cipher_info(value: str) -> ResourceCipherInfo | None:
    info = resource_cipher_info(value)
    return info if info is not None and info.purpose == 'provider' else None
