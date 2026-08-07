import secrets

API_KEY_BYTES = 32
API_KEY_MAX_LENGTH = 128
API_KEY_ROTATION_GRACE_SECONDS = 24 * 60 * 60


def generate_api_key() -> str:
    return f'ak_{secrets.token_urlsafe(API_KEY_BYTES)}'
