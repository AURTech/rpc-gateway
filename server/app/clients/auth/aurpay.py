import base64
import hashlib
import json
import time
from dataclasses import dataclass

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass(frozen=True)
class AurPayProfile:
    sub: str
    email: str
    name: str | None = None


def _decode_segment(value: str) -> bytes:
    padding_value = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(f'{value}{padding_value}')


def _int_from_segment(value: str) -> int:
    return int.from_bytes(_decode_segment(value), 'big')


def _audience_matches(audience: object, client_id: str, authorized_party: object) -> bool:
    if isinstance(audience, str):
        return audience == client_id
    if not isinstance(audience, list) or client_id not in audience:
        return False
    return len(audience) == 1 or authorized_party == client_id


def _json_object(value: object, error: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(error)
    return {str(key): item for key, item in value.items()}


def _find_signing_key(keys: object, kid: str) -> tuple[str, str]:
    if not isinstance(keys, list):
        raise ValueError('AurPay signing keys are invalid.')
    for candidate in keys:
        if not isinstance(candidate, dict):
            continue
        key = {str(name): value for name, value in candidate.items()}
        if key.get('kid') != kid or key.get('kty') != 'RSA' or key.get('use') != 'sig':
            continue
        modulus = key.get('n')
        exponent = key.get('e')
        if isinstance(modulus, str) and isinstance(exponent, str):
            return modulus, exponent
    raise ValueError('AurPay signing key is unavailable.')


def _validate_id_token(
    id_token: str,
    jwks: dict[str, object],
    *,
    issuer: str,
    client_id: str,
    nonce: str,
    access_token: str,
) -> dict[str, object]:
    encoded_header, encoded_claims, encoded_signature = id_token.split('.')
    header = _json_object(json.loads(_decode_segment(encoded_header)), 'AurPay ID token is invalid.')
    claims = _json_object(json.loads(_decode_segment(encoded_claims)), 'AurPay ID token is invalid.')
    kid = header.get('kid')
    if header.get('alg') != 'RS256' or not isinstance(kid, str):
        raise ValueError('AurPay ID token algorithm is invalid.')
    modulus, exponent = _find_signing_key(jwks.get('keys'), kid)
    public_key = rsa.RSAPublicNumbers(_int_from_segment(exponent), _int_from_segment(modulus)).public_key()
    try:
        public_key.verify(
            _decode_segment(encoded_signature),
            f'{encoded_header}.{encoded_claims}'.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise ValueError('AurPay ID token signature is invalid.') from exc

    now = int(time.time())
    expires_at = claims.get('exp')
    issued_at = claims.get('iat')
    if claims.get('iss') != issuer or not _audience_matches(claims.get('aud'), client_id, claims.get('azp')):
        raise ValueError('AurPay ID token issuer or audience is invalid.')
    if not isinstance(expires_at, int) or expires_at <= now - 60:
        raise ValueError('AurPay ID token has expired.')
    if not isinstance(issued_at, int) or issued_at > now + 60:
        raise ValueError('AurPay ID token issue time is invalid.')
    not_before = claims.get('nbf')
    if not_before is not None and (not isinstance(not_before, int) or not_before > now + 60):
        raise ValueError('AurPay ID token validity time is invalid.')
    sub = claims.get('sub')
    if claims.get('nonce') != nonce or not isinstance(sub, str) or not sub:
        raise ValueError('AurPay ID token binding is invalid.')
    token_hash = hashlib.sha256(access_token.encode()).digest()[:16]
    expected_at_hash = base64.urlsafe_b64encode(token_hash).decode().rstrip('=')
    if claims.get('at_hash') != expected_at_hash:
        raise ValueError('AurPay access token binding is invalid.')
    return claims


async def fetch_aurpay_profile(
    http_client: httpx.AsyncClient,
    code: str,
    code_verifier: str,
    nonce: str,
    *,
    issuer: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> AurPayProfile:
    issuer = issuer.rstrip('/')
    token_response = await http_client.post(
        f'{issuer}/oauth2/token',
        data={
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier,
        },
        auth=httpx.BasicAuth(client_id, client_secret),
        timeout=10,
    )
    token_response.raise_for_status()
    token_data = _json_object(token_response.json(), 'AurPay token response is invalid.')
    access_token = token_data['access_token']
    id_token = token_data['id_token']
    if (
        not isinstance(access_token, str)
        or not isinstance(id_token, str)
        or str(token_data.get('token_type', '')).lower() != 'bearer'
    ):
        raise ValueError('AurPay token response is invalid.')

    jwks_response = await http_client.get(f'{issuer}/oauth2/jwks.json', timeout=10)
    jwks_response.raise_for_status()
    claims = _validate_id_token(
        id_token,
        _json_object(jwks_response.json(), 'AurPay signing keys are invalid.'),
        issuer=issuer,
        client_id=client_id,
        nonce=nonce,
        access_token=access_token,
    )
    userinfo_response = await http_client.get(
        f'{issuer}/oauth2/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    userinfo_response.raise_for_status()
    userinfo = _json_object(userinfo_response.json(), 'AurPay user information is invalid.')
    sub = claims['sub']
    email = userinfo.get('email')
    if userinfo.get('sub') != sub or not isinstance(sub, str) or not isinstance(email, str):
        raise ValueError('AurPay user information is invalid.')
    name = userinfo.get('name')
    return AurPayProfile(
        sub=sub,
        email=email,
        name=name if isinstance(name, str) and name else None,
    )
