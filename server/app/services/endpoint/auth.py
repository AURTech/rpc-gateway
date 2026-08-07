from dataclasses import dataclass

from pydantic import SecretStr

from app.model.endpoint import (
    EndpointAuthType,
    EndpointBearerAuthCreateParams,
    EndpointBearerAuthUpdateParams,
    EndpointHeaderAuthCreateParams,
    EndpointHeaderAuthUpdateParams,
    EndpointNoAuthCreateParams,
    EndpointNoAuthUpdateParams,
    EndpointPathAuthCreateParams,
    EndpointPathAuthUpdateParams,
    EndpointQueryAuthCreateParams,
    EndpointQueryAuthUpdateParams,
    EndpointUpdateAuthParams,
)
from app.orm.endpoint import Endpoint
from app.services.endpoint.crypto import encrypt_endpoint_secret


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointAuthColumns:
    auth_type: EndpointAuthType
    auth_header_name: str | None
    auth_query_param: str | None
    encrypted_auth_secret: str | None

    def values(self) -> dict[str, object]:
        return {
            'auth_type': self.auth_type,
            'auth_header_name': self.auth_header_name,
            'auth_query_param': self.auth_query_param,
            'encrypted_auth_secret': self.encrypted_auth_secret,
        }


def _encrypted_secret(secret: SecretStr) -> str:
    return encrypt_endpoint_secret(secret.get_secret_value())


def build_create_auth(auth: object) -> EndpointAuthColumns:
    match auth:
        case EndpointNoAuthCreateParams():
            return EndpointAuthColumns(
                auth_type=EndpointAuthType.NONE,
                auth_header_name=None,
                auth_query_param=None,
                encrypted_auth_secret=None,
            )
        case EndpointHeaderAuthCreateParams(header_name=header_name, secret=secret):
            return EndpointAuthColumns(
                auth_type=EndpointAuthType.HEADER_API_KEY,
                auth_header_name=header_name,
                auth_query_param=None,
                encrypted_auth_secret=_encrypted_secret(secret),
            )
        case EndpointQueryAuthCreateParams(query_param=query_param, secret=secret):
            return EndpointAuthColumns(
                auth_type=EndpointAuthType.QUERY_API_KEY,
                auth_header_name=None,
                auth_query_param=query_param,
                encrypted_auth_secret=_encrypted_secret(secret),
            )
        case EndpointPathAuthCreateParams(secret=secret):
            return EndpointAuthColumns(
                auth_type=EndpointAuthType.PATH_API_KEY,
                auth_header_name=None,
                auth_query_param=None,
                encrypted_auth_secret=_encrypted_secret(secret),
            )
        case EndpointBearerAuthCreateParams(secret=secret):
            return EndpointAuthColumns(
                auth_type=EndpointAuthType.BEARER,
                auth_header_name=None,
                auth_query_param=None,
                encrypted_auth_secret=_encrypted_secret(secret),
            )
        case _:
            raise ValueError('Endpoint auth configuration is invalid.')


def create_auth_changed_fields(columns: EndpointAuthColumns) -> list[str]:
    changed_fields = ['auth_type']
    if columns.auth_header_name is not None:
        changed_fields.append('auth_header_name')
    if columns.auth_query_param is not None:
        changed_fields.append('auth_query_param')
    if columns.encrypted_auth_secret is not None:
        changed_fields.append('auth_secret')
    return changed_fields


def _updated_encrypted_secret(
    endpoint: Endpoint,
    secret: SecretStr | None,
    *,
    auth_type_changed: bool,
) -> str:
    if secret is not None:
        return _encrypted_secret(secret)
    if auth_type_changed or not endpoint.encrypted_auth_secret:
        raise ValueError('Endpoint auth secret is required when auth type changes.')
    return endpoint.encrypted_auth_secret


def _build_update_auth(endpoint: Endpoint, auth: EndpointUpdateAuthParams) -> EndpointAuthColumns:
    stored_auth_type = EndpointAuthType(endpoint.auth_type)
    match auth:
        case EndpointNoAuthUpdateParams():
            return EndpointAuthColumns(
                auth_type=EndpointAuthType.NONE,
                auth_header_name=None,
                auth_query_param=None,
                encrypted_auth_secret=None,
            )
        case EndpointHeaderAuthUpdateParams(header_name=header_name, secret=secret):
            auth_type = EndpointAuthType.HEADER_API_KEY
            auth_type_changed = auth_type is not stored_auth_type
            effective_header = header_name if header_name is not None else endpoint.auth_header_name
            if auth_type_changed and header_name is None:
                effective_header = None
            if not effective_header:
                raise ValueError('Endpoint auth header name is required when auth type changes.')
            return EndpointAuthColumns(
                auth_type=auth_type,
                auth_header_name=effective_header,
                auth_query_param=None,
                encrypted_auth_secret=_updated_encrypted_secret(
                    endpoint,
                    secret,
                    auth_type_changed=auth_type_changed,
                ),
            )
        case EndpointQueryAuthUpdateParams(query_param=query_param, secret=secret):
            auth_type = EndpointAuthType.QUERY_API_KEY
            auth_type_changed = auth_type is not stored_auth_type
            effective_query = query_param if query_param is not None else endpoint.auth_query_param
            if auth_type_changed and query_param is None:
                effective_query = None
            if not effective_query:
                raise ValueError('Endpoint auth query parameter is required when auth type changes.')
            return EndpointAuthColumns(
                auth_type=auth_type,
                auth_header_name=None,
                auth_query_param=effective_query,
                encrypted_auth_secret=_updated_encrypted_secret(
                    endpoint,
                    secret,
                    auth_type_changed=auth_type_changed,
                ),
            )
        case EndpointPathAuthUpdateParams(secret=secret):
            auth_type = EndpointAuthType.PATH_API_KEY
        case EndpointBearerAuthUpdateParams(secret=secret):
            auth_type = EndpointAuthType.BEARER
        case _:
            raise ValueError('Endpoint auth configuration is invalid.')
    auth_type_changed = auth_type is not stored_auth_type
    return EndpointAuthColumns(
        auth_type=auth_type,
        auth_header_name=None,
        auth_query_param=None,
        encrypted_auth_secret=_updated_encrypted_secret(
            endpoint,
            secret,
            auth_type_changed=auth_type_changed,
        ),
    )


def auth_update_values(endpoint: Endpoint, auth: EndpointUpdateAuthParams) -> tuple[dict[str, object], list[str]]:
    columns = _build_update_auth(endpoint, auth)
    values: dict[str, object] = {}
    changed_fields: list[str] = []
    if columns.auth_type is not EndpointAuthType(endpoint.auth_type):
        values['auth_type'] = columns.auth_type
        changed_fields.append('auth_type')
    if columns.auth_header_name != endpoint.auth_header_name:
        values['auth_header_name'] = columns.auth_header_name
        changed_fields.append('auth_header_name')
    if columns.auth_query_param != endpoint.auth_query_param:
        values['auth_query_param'] = columns.auth_query_param
        changed_fields.append('auth_query_param')
    if columns.encrypted_auth_secret != endpoint.encrypted_auth_secret:
        values['encrypted_auth_secret'] = columns.encrypted_auth_secret
        changed_fields.append('auth_secret')
    return values, changed_fields
