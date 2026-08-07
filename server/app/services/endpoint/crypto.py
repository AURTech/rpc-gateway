from app.core.resource_secret import (
    ResourceSecretConfigError,
    decrypt_resource_secret,
    encrypt_resource_secret,
    rekey_resource_secret,
)

EndpointSecretConfigError = ResourceSecretConfigError


def encrypt_endpoint_secret(secret: str) -> str:
    value = secret.strip()
    if not value:
        raise ValueError('Endpoint auth secret cannot be empty.')
    return encrypt_resource_secret(value, purpose='auth')


def decrypt_endpoint_secret(encrypted_secret: str) -> str:
    return decrypt_resource_secret(encrypted_secret, purpose='auth')


def encrypt_endpoint_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ValueError('Endpoint URL cannot be empty.')
    return encrypt_resource_secret(value, purpose='url')


def decrypt_endpoint_url(encrypted_url: str) -> str:
    value = encrypted_url.strip()
    if not value:
        raise EndpointSecretConfigError('Endpoint URL is unavailable.')
    return decrypt_resource_secret(value, purpose='url')


def rekey_endpoint_secret(encrypted_secret: str) -> str:
    return rekey_resource_secret(encrypted_secret, purpose='auth')


def rekey_endpoint_url(encrypted_url: str) -> str:
    return rekey_resource_secret(encrypted_url, purpose='url')
