from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

CSRF_HEADER = {'X-RPC-Gateway-CSRF': '1'}


@dataclass(slots=True, kw_only=True)
class EndpointResource:
    id: str
    version: int
    chain: str
    protocol: str


@dataclass(slots=True, kw_only=True)
class RouteResource:
    id: str
    version: int


class GatewayClient:
    def __init__(self, api_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=api_url, timeout=httpx.Timeout(30))

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self, email: str, password: str) -> dict[str, Any]:
        response = await self._client.post('/v2/auth/login', json={'email': email, 'password': password})
        return self._data(response, 200)

    async def logout(self) -> None:
        response = await self._client.post('/v2/auth/logout', headers=CSRF_HEADER)
        self._data(response, 200)

    async def create_app(self, name: str) -> dict[str, Any]:
        response = await self._client.post('/v2/apps', headers=CSRF_HEADER, json={'name': name, 'enabled': True})
        return self._data(response, 201)

    async def list_gateways(self, app_id: str) -> list[dict[str, Any]]:
        response = await self._client.get('/v2/gateways', params={'app_id': app_id, 'size': 50})
        data = self._data(response, 200)
        items = data.get('items')
        if not isinstance(items, list):
            raise RuntimeError('Gateway list response is invalid.')
        return items

    async def create_endpoint(
        self,
        *,
        name: str,
        chain: str,
        network: str,
        protocol: str,
        url: str,
    ) -> EndpointResource:
        response = await self._client.post(
            '/v2/endpoints',
            headers=CSRF_HEADER,
            json={
                'name': name,
                'chain': chain,
                'network': network,
                'protocol': protocol,
                'url': url,
                'enabled': True,
                'trust_level': 'unverified',
                'auth': {'type': 'none'},
            },
        )
        data = self._data(response, 201)
        return EndpointResource(id=data['id'], version=data['version'], chain=chain, protocol=protocol)

    async def update_endpoint_url(self, endpoint: EndpointResource, url: str) -> EndpointResource:
        response = await self._client.patch(
            f'/v2/endpoints/{endpoint.id}',
            headers=CSRF_HEADER,
            json={'expected_version': endpoint.version, 'url': url},
        )
        data = self._data(response, 200)
        return EndpointResource(
            id=data['id'],
            version=data['version'],
            chain=endpoint.chain,
            protocol=endpoint.protocol,
        )

    async def get_jsonrpc_route(self, gateway_id: str) -> RouteResource:
        response = await self._client.get(f'/v2/gateways/{gateway_id}/jsonrpc-route')
        data = self._data(response, 200)
        return RouteResource(id=data['id'], version=data['version'])

    async def replace_jsonrpc_route(
        self,
        gateway_id: str,
        route: RouteResource,
        endpoint_ids: list[str],
        *,
        max_attempts: int = 2,
    ) -> RouteResource:
        response = await self._client.put(
            f'/v2/gateways/{gateway_id}/jsonrpc-route',
            headers=CSRF_HEADER,
            json={
                'expected_version': route.version,
                'minimum_trust': 'unverified',
                'max_latency_ms': None,
                'max_attempts': max_attempts,
                'retry_policy': 'idempotent',
                'strategy': {
                    'type': 'priority_failover',
                    'targets': [{'endpoint_id': endpoint_id} for endpoint_id in endpoint_ids],
                },
            },
        )
        data = self._data(response, 200)
        return RouteResource(id=data['id'], version=data['version'])

    async def get_http_route(self, gateway_id: str) -> RouteResource:
        response = await self._client.get(f'/v2/gateways/{gateway_id}/http-api-route')
        data = self._data(response, 200)
        return RouteResource(id=data['id'], version=data['version'])

    async def replace_http_route(
        self,
        gateway_id: str,
        route: RouteResource,
        endpoint_ids: list[str],
    ) -> RouteResource:
        response = await self._client.put(
            f'/v2/gateways/{gateway_id}/http-api-route',
            headers=CSRF_HEADER,
            json={
                'expected_version': route.version,
                'minimum_trust': 'unverified',
                'max_latency_ms': None,
                'max_attempts': 2,
                'retry_policy': 'idempotent',
                'strategy': {
                    'type': 'priority_failover',
                    'targets': [{'endpoint_id': endpoint_id} for endpoint_id in endpoint_ids],
                },
            },
        )
        data = self._data(response, 200)
        return RouteResource(id=data['id'], version=data['version'])

    async def create_method_route(
        self,
        gateway_id: str,
        methods: list[str],
        endpoint_id: str,
    ) -> RouteResource:
        response = await self._client.post(
            f'/v2/gateways/{gateway_id}/jsonrpc-method-routes',
            headers=CSRF_HEADER,
            json={
                'methods': methods,
                'minimum_trust': 'unverified',
                'max_latency_ms': None,
                'max_attempts': 1,
                'retry_policy': 'idempotent',
                'strategy': {'type': 'priority_failover', 'targets': [{'endpoint_id': endpoint_id}]},
            },
        )
        data = self._data(response, 201)
        return RouteResource(id=data['id'], version=data['version'])

    async def delete_method_route(self, gateway_id: str, route: RouteResource) -> None:
        response = await self._client.delete(
            f'/v2/gateways/{gateway_id}/jsonrpc-method-routes/{route.id}',
            headers=CSRF_HEADER,
            params={'expected_version': route.version},
        )
        self._data(response, 200)

    async def delete_endpoint(self, endpoint_id: str) -> None:
        response = await self._client.delete(f'/v2/endpoints/{endpoint_id}', headers=CSRF_HEADER)
        self._data(response, 200)

    async def delete_app(self, app_id: str) -> None:
        response = await self._client.delete(f'/v2/apps/{app_id}', headers=CSRF_HEADER)
        self._data(response, 200)

    async def get_jsonrpc_policy(self) -> dict[str, Any]:
        response = await self._client.get('/v2/jsonrpc-rate-limit-policy')
        return self._data(response, 200)

    async def update_jsonrpc_policy(self, values: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.patch('/v2/jsonrpc-rate-limit-policy', headers=CSRF_HEADER, json=values)
        return self._data(response, 200)

    async def get_usage(self, resource: str, params: dict[str, str | int | float | None]) -> dict[str, Any]:
        response = await self._client.get(f'/v2/usage/{resource}', params=params)
        return self._data(response, 200)

    async def jsonrpc(
        self,
        gateway: dict[str, Any],
        api_key: str | None,
        payload: object,
        *,
        raw: bytes | None = None,
    ) -> httpx.Response:
        access = self._access_point(gateway, 'jsonrpc')
        path = '/' if api_key is None else f'/{quote(api_key, safe="")}'
        content = raw if raw is not None else None
        return await self._client.post(
            path,
            headers={'Host': access.hostname or '', 'Content-Type': 'application/json'},
            json=None if content is not None else payload,
            content=content,
            timeout=20,
        )

    async def http_api(
        self,
        gateway: dict[str, Any],
        api_key: str,
        method: str,
        path: str,
    ) -> httpx.Response:
        access = self._access_point(gateway, 'http_api')
        request_path = f'/{quote(api_key, safe="")}/{path.lstrip("/")}'
        return await self._client.request(method, request_path, headers={'Host': access.hostname or ''}, timeout=20)

    @staticmethod
    def _access_point(gateway: dict[str, Any], transport: str):
        points = gateway.get('access_points')
        if not isinstance(points, list):
            raise RuntimeError('Gateway access points are invalid.')
        for point in points:
            if isinstance(point, dict) and point.get('transport') == transport and isinstance(point.get('url'), str):
                return urlsplit(point['url'])
        raise RuntimeError(f'Gateway has no {transport} access point.')

    @staticmethod
    def _data(response: httpx.Response, expected_status: int) -> dict[str, Any]:
        if response.status_code != expected_status:
            raise RuntimeError(f'Control API returned {response.status_code}: {response.text[:500]}')
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('msg') != 'ok' or not isinstance(payload.get('data'), dict):
            raise RuntimeError('Control API response envelope is invalid.')
        return payload['data']
