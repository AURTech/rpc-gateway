from app.clients.endpoint import EndpointConnection
from app.clients.transport import HttpAuth, inject_path_api_key
from app.model.endpoint import EndpointAuthType
from app.orm.endpoint import Endpoint
from app.services.endpoint.crypto import decrypt_endpoint_secret, decrypt_endpoint_url


def _endpoint_auth(endpoint: Endpoint) -> tuple[EndpointAuthType, str | None]:
    auth_type = EndpointAuthType(endpoint.auth_type)
    secret = decrypt_endpoint_secret(endpoint.encrypted_auth_secret) if endpoint.encrypted_auth_secret else None
    return auth_type, secret


def build_endpoint_connection(endpoint: Endpoint) -> EndpointConnection:
    auth_type, secret = _endpoint_auth(endpoint)
    name: str | None = None
    if auth_type is EndpointAuthType.HEADER_API_KEY:
        name = endpoint.auth_header_name
    elif auth_type is EndpointAuthType.QUERY_API_KEY:
        name = endpoint.auth_query_param
    auth = HttpAuth(type=auth_type, secret=secret, name=name)
    return EndpointConnection(url=decrypt_endpoint_url(endpoint.encrypted_url), auth=auth)


def build_endpoint_url(endpoint: Endpoint) -> str:
    auth_type = EndpointAuthType(endpoint.auth_type)
    url = decrypt_endpoint_url(endpoint.encrypted_url)
    if auth_type is not EndpointAuthType.PATH_API_KEY:
        return url
    if not endpoint.encrypted_auth_secret:
        raise ValueError('Endpoint encrypted auth secret is unavailable.')

    secret = decrypt_endpoint_secret(endpoint.encrypted_auth_secret)
    return inject_path_api_key(url, secret)
