import base64
import binascii
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import CONF

_CIPHER_PREFIX = 'appkey'
_CIPHER_FORMAT_VERSION = 'v1'
_NONCE_BYTES = 12
_HKDF_SALT = b'rpc-gateway/app-api-key/v1'


class AppKeyCryptoError(Exception):
    pass


def digest_api_key(api_key: str) -> str:
    if not api_key:
        raise ValueError('API Key cannot be empty.')
    return hmac.new(_derive_key('lookup'), api_key.encode(), hashlib.sha256).hexdigest()


def encrypt_api_key(api_key: str, *, app_id: str, key_id: str) -> str:
    if not api_key:
        raise ValueError('API Key cannot be empty.')
    header = _envelope_header()
    key = _derive_key('encryption')
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, api_key.encode(), _associated_data(header, app_id, key_id))
    token = base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip('=')
    return f'{header}:{token}'


def decrypt_api_key(encrypted_api_key: str, *, app_id: str, key_id: str) -> str:
    header, payload = _parse_ciphertext(encrypted_api_key)
    key = _derive_key('encryption')
    try:
        plaintext = AESGCM(key).decrypt(
            payload[:_NONCE_BYTES],
            payload[_NONCE_BYTES:],
            _associated_data(header, app_id, key_id),
        )
        return plaintext.decode()
    except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
        raise AppKeyCryptoError('Encrypted App API Key cannot be decrypted.') from exc


def _parse_ciphertext(value: str) -> tuple[str, bytes]:
    parts = value.split(':', 2)
    if len(parts) != 3:
        raise AppKeyCryptoError('Encrypted App API Key is invalid.')
    prefix, format_version, token = parts
    if prefix != _CIPHER_PREFIX or format_version != _CIPHER_FORMAT_VERSION or not token:
        raise AppKeyCryptoError('Encrypted App API Key is invalid.')
    try:
        padding = '=' * (-len(token) % 4)
        payload = base64.b64decode(f'{token}{padding}', altchars=b'-_', validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppKeyCryptoError('Encrypted App API Key is invalid.') from exc
    if len(payload) <= _NONCE_BYTES:
        raise AppKeyCryptoError('Encrypted App API Key is invalid.')
    return _envelope_header(), payload


def _envelope_header() -> str:
    return f'{_CIPHER_PREFIX}:{_CIPHER_FORMAT_VERSION}'


def _associated_data(header: str, app_id: str, key_id: str) -> bytes:
    # The v1 label is part of persisted ciphertext authentication and is unrelated to the removed HTTP reveal flow.
    return f'{header}:app:{app_id}:key:{key_id}:purpose:reveal'.encode()


@lru_cache(maxsize=2)
def _derive_key(purpose: str) -> bytes:
    info = f'rpc-gateway/app-api-key/{purpose}/v1'.encode()
    master_key = CONF.APP_API_KEY_MASTER_KEY.get_secret_value()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT, info=info).derive(master_key)
