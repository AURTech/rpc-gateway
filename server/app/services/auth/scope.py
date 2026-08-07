from collections.abc import Mapping
from types import MappingProxyType

from fastapi import Request

from app.core.errors import ForbiddenError
from app.model.auth import AuthIdentity, PersonalAccessTokenScope

S = PersonalAccessTokenScope

_ROUTE_SCOPES: Mapping[str, frozenset[PersonalAccessTokenScope]] = MappingProxyType(
    {
        'me': frozenset(),
        'get_overview': frozenset({S.OVERVIEW_READ}),
        'create_app': frozenset({S.APPS_WRITE, S.APP_KEYS_WRITE}),
        'list_apps': frozenset({S.APPS_READ}),
        'get_app': frozenset({S.APPS_READ}),
        'update_app': frozenset({S.APPS_WRITE}),
        'delete_app': frozenset({S.APPS_WRITE}),
        'list_api_keys': frozenset({S.APP_KEYS_READ}),
        'rotate_api_key': frozenset({S.APP_KEYS_WRITE}),
        'revoke_api_key': frozenset({S.APP_KEYS_WRITE}),
        'bulk_update_app_gateways': frozenset({S.GATEWAYS_WRITE}),
        'list_gateways': frozenset({S.GATEWAYS_READ}),
        'get_gateway': frozenset({S.GATEWAYS_READ}),
        'update_gateway': frozenset({S.GATEWAYS_WRITE}),
        'create_endpoint': frozenset({S.ENDPOINTS_WRITE}),
        'list_endpoints': frozenset({S.ENDPOINTS_READ}),
        'get_endpoint': frozenset({S.ENDPOINTS_READ}),
        'update_endpoint': frozenset({S.ENDPOINTS_WRITE}),
        'delete_endpoint': frozenset({S.ENDPOINTS_WRITE}),
        'bulk_delete_endpoints': frozenset({S.ENDPOINTS_WRITE}),
        'check_endpoint_health': frozenset({S.ENDPOINTS_WRITE}),
        'list_endpoint_audit_events': frozenset({S.ENDPOINTS_READ}),
        'create_provider': frozenset({S.PROVIDERS_WRITE}),
        'list_providers': frozenset({S.PROVIDERS_READ}),
        'get_provider': frozenset({S.PROVIDERS_READ}),
        'update_provider': frozenset({S.PROVIDERS_WRITE}),
        'delete_provider': frozenset({S.PROVIDERS_WRITE}),
        'sync_provider': frozenset({S.PROVIDERS_WRITE}),
        'list_provider_endpoints': frozenset({S.PROVIDERS_READ}),
        'get_default_route': frozenset({S.ROUTES_READ}),
        'replace_default_route': frozenset({S.ROUTES_WRITE}),
        'list_method_routes': frozenset({S.ROUTES_READ}),
        'create_method_route': frozenset({S.ROUTES_WRITE}),
        'replace_method_route': frozenset({S.ROUTES_WRITE}),
        'delete_method_route': frozenset({S.ROUTES_WRITE}),
        'get_http_api_route': frozenset({S.ROUTES_READ}),
        'replace_http_api_route': frozenset({S.ROUTES_WRITE}),
        'get_usage_summary': frozenset({S.USAGE_READ}),
        'get_usage_series': frozenset({S.USAGE_READ}),
        'get_usage_methods': frozenset({S.USAGE_READ}),
        'get_usage_networks': frozenset({S.USAGE_READ}),
        'list_jsonrpc_methods': frozenset({S.META_READ}),
        'create_account': frozenset({S.ACCOUNTS_WRITE}),
        'list_accounts': frozenset({S.ACCOUNTS_READ}),
        'get_account': frozenset({S.ACCOUNTS_READ}),
        'update_account': frozenset({S.ACCOUNTS_WRITE}),
        'archive_accounts': frozenset({S.ACCOUNTS_WRITE}),
        'get_rate_limit_policy': frozenset({S.POLICIES_READ}),
        'update_rate_limit_policy': frozenset({S.POLICIES_WRITE}),
        'list_rate_limit_audits': frozenset({S.POLICIES_READ}),
    }
)


def validate_pat_scopes(request: Request, identity: AuthIdentity) -> None:
    if not identity.uses_pat:
        return
    route = request.scope.get('route')
    route_name = getattr(route, 'name', None)
    required = _ROUTE_SCOPES.get(route_name) if isinstance(route_name, str) else None
    if required is None:
        raise ForbiddenError(
            'Personal access tokens cannot call this endpoint.',
            code='auth.pat_not_allowed',
        )
    missing = required - identity.pat_scopes
    if missing:
        required_values = sorted(scope.value for scope in required)
        raise ForbiddenError(
            'Personal access token scope is insufficient.',
            code='auth.insufficient_scope',
            details={'required_scopes': required_values},
        )


def pat_scopes_for_route(route_name: str) -> list[str] | None:
    scopes = _ROUTE_SCOPES.get(route_name)
    return sorted(scope.value for scope in scopes) if scopes is not None else None
