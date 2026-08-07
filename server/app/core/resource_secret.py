import base64
import binascii
import secrets
from dataclasses import dataclass
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import CONF, normalize_endpoint_key_version, normalize_endpoint_keyring

_CIPHER_PREFIX = 'endpoint'
_CIPHER_FORMAT_VERSION = 'v1'
_NONCE_BYTES = 12
_HKDF_SALT = b'rpc-gateway/endpoint/aead/v1'

ResourceSecretPurpose = Literal['auth', 'url', 'provider']


class ResourceSecretConfigError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ResourceCipherInfo:
    key_version: str
    purpose: ResourceSecretPurpose


@dataclass(frozen=True, slots=True)
class _ResourceKeyring:
    active_version: str
    keys: dict[str, str]


def encrypt_resource_secret(value: str, *, purpose: ResourceSecretPurpose) -> str:
    keyring = _load_keyring()
    version = keyring.active_version
    header = _envelope_header(version, purpose)
    key = _derive_key(keyring.keys[version], key_version=version, purpose=purpose)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode(), header.encode())
    token = base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip('=')
    return f'{header}:{token}'


def decrypt_resource_secret(value: str, *, purpose: ResourceSecretPurpose) -> str:
    header, key_version, stored_purpose, payload = _parse_ciphertext(value)
    if stored_purpose != purpose:
        raise ResourceSecretConfigError('Encrypted value cannot be decrypted.')
    keyring = _load_keyring()
    master_key = keyring.keys.get(key_version)
    if master_key is None:
        raise ResourceSecretConfigError('Encryption key version is unavailable.')
    key = _derive_key(master_key, key_version=key_version, purpose=purpose)
    try:
        plaintext = AESGCM(key).decrypt(payload[:_NONCE_BYTES], payload[_NONCE_BYTES:], header.encode())
        return plaintext.decode()
    except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
        raise ResourceSecretConfigError('Encrypted value cannot be decrypted.') from exc


def rekey_resource_secret(value: str, *, purpose: ResourceSecretPurpose) -> str:
    info = resource_cipher_info(value)
    keyring = _load_keyring()
    if info is not None and info.key_version == keyring.active_version and info.purpose == purpose:
        decrypt_resource_secret(value, purpose=purpose)
        return value
    plaintext = decrypt_resource_secret(value, purpose=purpose)
    return encrypt_resource_secret(plaintext, purpose=purpose)


def resource_cipher_info(value: str) -> ResourceCipherInfo | None:
    if not value.startswith(f'{_CIPHER_PREFIX}:'):
        return None
    _, _, key_version, purpose, _ = _parse_envelope(value)
    return ResourceCipherInfo(key_version=key_version, purpose=purpose)


def _parse_ciphertext(value: str) -> tuple[str, str, ResourceSecretPurpose, bytes]:
    prefix, format_version, key_version, purpose, token = _parse_envelope(value)
    header = f'{prefix}:{format_version}:{key_version}:{purpose}'
    try:
        padding = '=' * (-len(token) % 4)
        payload = base64.b64decode(f'{token}{padding}', altchars=b'-_', validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ResourceSecretConfigError('Encrypted value is invalid.') from exc
    if len(payload) <= _NONCE_BYTES:
        raise ResourceSecretConfigError('Encrypted value is invalid.')
    return header, key_version, purpose, payload


def _parse_envelope(value: str) -> tuple[str, str, str, ResourceSecretPurpose, str]:
    parts = value.split(':', 4)
    if len(parts) != 5:
        raise ResourceSecretConfigError('Encrypted value is invalid.')
    prefix, format_version, key_version, purpose, token = parts
    if prefix != _CIPHER_PREFIX or format_version != _CIPHER_FORMAT_VERSION:
        raise ResourceSecretConfigError('Encrypted value is invalid.')
    try:
        key_version = normalize_endpoint_key_version(key_version)
    except ValueError as exc:
        raise ResourceSecretConfigError('Encrypted value is invalid.') from exc
    if not token:
        raise ResourceSecretConfigError('Encrypted value is invalid.')
    if purpose == 'auth':
        typed_purpose: ResourceSecretPurpose = 'auth'
    elif purpose == 'url':
        typed_purpose = 'url'
    elif purpose == 'provider':
        typed_purpose = 'provider'
    else:
        raise ResourceSecretConfigError('Encrypted value is invalid.')
    return prefix, format_version, key_version, typed_purpose, token


def _envelope_header(key_version: str, purpose: ResourceSecretPurpose) -> str:
    return f'{_CIPHER_PREFIX}:{_CIPHER_FORMAT_VERSION}:{key_version}:{purpose}'


def _derive_key(master_key: str, *, key_version: str, purpose: ResourceSecretPurpose) -> bytes:
    info = f'rpc-gateway/endpoint/{key_version}/{purpose}'.encode()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT, info=info).derive(master_key.encode())


def _load_keyring() -> _ResourceKeyring:
    try:
        active_version = normalize_endpoint_key_version(CONF.ENDPOINT_ACTIVE_KEY_VERSION)
        keys = normalize_endpoint_keyring(CONF.ENDPOINT_KEYRING)
    except ValueError as exc:
        raise ResourceSecretConfigError(str(exc)) from exc
    if not keys:
        raise ResourceSecretConfigError('Encryption keyring is not configured.')
    if active_version not in keys:
        raise ResourceSecretConfigError('Active encryption key version is unavailable.')
    return _ResourceKeyring(active_version=active_version, keys=keys)
