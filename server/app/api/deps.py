from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Cookie, Depends, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth_context import reset_pat_id, set_pat_id
from app.core.errors import ForbiddenError
from app.model.auth import AuthIdentity, IdentityType
from app.services.auth import AuthManager
from app.services.auth.csrf import validate_csrf_request
from app.services.auth.scope import validate_pat_scopes
from app.services.auth.session import OAUTH_STATE_COOKIE_NAME, SESSION_COOKIE_NAME
from app.services.auth.token import PersonalAccessTokenManager
from app.services.endpoint import EndpointHealthManager, EndpointManager
from app.services.http_api_rate_limit import HttpApiRateLimitPolicyManager
from app.services.jsonrpc_rate_limit.policy import JsonRpcRateLimitPolicyManager
from app.services.provider import ProviderManager
from app.services.public import PublicJsonRpcManager

session_cookie = APIKeyCookie(name=SESSION_COOKIE_NAME, scheme_name='SessionCookie', auto_error=False)
pat_bearer = HTTPBearer(scheme_name='PersonalAccessToken', bearerFormat='PAT', auto_error=False)
SessionCookieValue = Annotated[str | None, Security(session_cookie)]
PatBearerValue = Annotated[HTTPAuthorizationCredentials | None, Security(pat_bearer)]
OAuthStateCookieValue = Annotated[str | None, Cookie(alias=OAUTH_STATE_COOKIE_NAME)]


def get_auth_manager(request: Request) -> AuthManager:
    return request.app.state.auth_manager


def get_provider_manager(request: Request) -> ProviderManager:
    return request.app.state.provider_manager


def get_endpoint_health_manager(request: Request) -> EndpointHealthManager:
    return request.app.state.endpoint_health_manager


def get_endpoint_manager(request: Request) -> EndpointManager:
    return request.app.state.endpoint_manager


def get_public_jsonrpc_manager(request: Request) -> PublicJsonRpcManager:
    return request.app.state.public_jsonrpc_manager


def get_jsonrpc_rate_manager(request: Request) -> JsonRpcRateLimitPolicyManager:
    return request.app.state.jsonrpc_rate_limit_policy_manager


def get_http_rate_manager(request: Request) -> HttpApiRateLimitPolicyManager:
    return request.app.state.http_api_rate_limit_policy_manager


AuthManagerDep = Annotated[AuthManager, Depends(get_auth_manager)]
ProviderManagerDep = Annotated[ProviderManager, Depends(get_provider_manager)]
EndpointHealthManagerDep = Annotated[EndpointHealthManager, Depends(get_endpoint_health_manager)]
EndpointManagerDep = Annotated[EndpointManager, Depends(get_endpoint_manager)]
PublicJsonRpcManagerDep = Annotated[PublicJsonRpcManager, Depends(get_public_jsonrpc_manager)]
JsonRpcRateLimitPolicyManagerDep = Annotated[JsonRpcRateLimitPolicyManager, Depends(get_jsonrpc_rate_manager)]
HttpApiRateLimitPolicyManagerDep = Annotated[HttpApiRateLimitPolicyManager, Depends(get_http_rate_manager)]


async def get_auth_identity(
    request: Request,
    rpc_gateway_session: SessionCookieValue,
    pat: PatBearerValue,
    auth_manager: AuthManagerDep,
) -> AsyncGenerator[AuthIdentity]:
    if rpc_gateway_session is not None and pat is not None:
        raise ForbiddenError('Use either a session cookie or a personal access token.', code='auth.multiple_credentials')
    if pat is not None:
        identity = await PersonalAccessTokenManager.authenticate(pat.credentials)
        validate_pat_scopes(request, identity)
        request.state.pat_id = identity.pat_id
    else:
        identity = await auth_manager.get_auth_identity(rpc_gateway_session)
        validate_csrf_request(request)
    context_token = set_pat_id(identity.pat_id)
    try:
        yield identity
    finally:
        reset_pat_id(context_token)


async def get_session_identity(
    request: Request,
    rpc_gateway_session: SessionCookieValue,
    auth_manager: AuthManagerDep,
) -> AuthIdentity:
    if request.headers.get('authorization'):
        raise ForbiddenError('Use either a session cookie or a personal access token.', code='auth.multiple_credentials')
    identity = await auth_manager.get_auth_identity(rpc_gateway_session)
    validate_csrf_request(request)
    return identity


async def get_admin_identity(
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
) -> AuthIdentity:
    if identity.identity_type is not IdentityType.ADMIN:
        raise ForbiddenError('Admin permission required.')
    return identity


async def get_account_identity(
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
) -> AuthIdentity:
    if identity.identity_type not in {IdentityType.USER, IdentityType.ADMIN}:
        raise ForbiddenError('Account permission required.')
    return identity


def validate_logout_csrf(request: Request, rpc_gateway_session: SessionCookieValue) -> None:
    if rpc_gateway_session is not None:
        validate_csrf_request(request)


AuthIdentityDep = Annotated[AuthIdentity, Depends(get_auth_identity)]
SessionIdentityDep = Annotated[AuthIdentity, Depends(get_session_identity)]
AdminIdentityDep = Annotated[AuthIdentity, Depends(get_admin_identity)]
AccountIdentityDep = Annotated[AuthIdentity, Depends(get_account_identity)]
LogoutCsrfDep = Annotated[None, Depends(validate_logout_csrf)]
