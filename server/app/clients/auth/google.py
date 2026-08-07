from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    avatar_url: str | None = None


async def fetch_google_profile(
    http_client: httpx.AsyncClient,
    code: str,
    code_verifier: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> GoogleProfile:
    token_response = await http_client.post(
        'https://oauth2.googleapis.com/token',
        data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier,
        },
        timeout=10,
    )
    token_response.raise_for_status()
    access_token = token_response.json()['access_token']
    userinfo_response = await http_client.get(
        'https://openidconnect.googleapis.com/v1/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    userinfo_response.raise_for_status()
    data = userinfo_response.json()
    return GoogleProfile(
        sub=data['sub'],
        email=data['email'],
        email_verified=bool(data.get('email_verified')),
        name=data.get('name'),
        avatar_url=data.get('picture'),
    )
