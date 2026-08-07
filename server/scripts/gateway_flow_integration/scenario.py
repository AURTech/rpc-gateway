import asyncio
import hashlib
import math
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
import orjson
from app.model.blockchain import Chain, Network
from app.model.runtime_state.tip import Finality, TipUnit
from scripts.gateway_flow_integration.client import EndpointResource, GatewayClient, RouteResource
from scripts.gateway_flow_integration.inspector import (
    PostgresRetentionAuditSpec,
    RedisTtlAuditSpec,
    RuntimeInspector,
    TipAuditSpec,
)
from scripts.gateway_flow_integration.publisher_oracle import LedgerExpectation, jsonrpc_expectation
from scripts.gateway_flow_integration.usage_audit import UsageAuditor, UsageCallSpec

CHAINS = (
    (Chain.ETHEREUM, Network.MAINNET),
    (Chain.POLYGON, Network.MAINNET),
    (Chain.BSC, Network.MAINNET),
    (Chain.ARBITRUM, Network.MAINNET),
    (Chain.OPTIMISM, Network.MAINNET),
    (Chain.BASE, Network.MAINNET),
    (Chain.SOLANA, Network.MAINNET_BETA),
    (Chain.BITCOIN, Network.MAINNET),
    (Chain.LITECOIN, Network.MAINNET),
    (Chain.TRON, Network.MAINNET),
)
HEIGHTS = {
    Chain.ETHEREUM: 20_000_000,
    Chain.POLYGON: 60_000_000,
    Chain.BSC: 40_000_000,
    Chain.ARBITRUM: 250_000_000,
    Chain.OPTIMISM: 130_000_000,
    Chain.BASE: 25_000_000,
    Chain.SOLANA: 300_000_000,
    Chain.BITCOIN: 900_000,
    Chain.LITECOIN: 3_000_000,
    Chain.TRON: 75_000_000,
}
ADMIN_EMAIL = 'admin@example.test'
ADMIN_PASSWORD = 'tiTjpKS46zN8RnpAaulIOsW2'
USER_EMAIL = 'u1@example.test'
USER_PASSWORD = 'vUByYtF1nH8czcIDwOr8mw4t'
CACHE_HEADER = 'X-RPC-Gateway-Cache'


@dataclass(slots=True, kw_only=True)
class ChainResources:
    gateway: dict[str, Any]
    route: RouteResource
    bad: EndpointResource
    good: tuple[EndpointResource, EndpointResource, EndpointResource]


@dataclass(slots=True, kw_only=True)
class AccountResources:
    app_id: str
    api_key: str
    gateways: dict[Chain, dict[str, Any]]
    endpoints: list[EndpointResource]
    routes: dict[Chain, RouteResource]
    http_route: RouteResource | None = None


type AdminEndpointMap = dict[
    Chain,
    tuple[EndpointResource, tuple[EndpointResource, EndpointResource, EndpointResource]],
]


def _gateway_map(items: list[dict[str, Any]]) -> dict[Chain, dict[str, Any]]:
    if len(items) != 20:
        raise RuntimeError(f'App should create 20 Gateways, got {len(items)}.')
    wanted = {(chain.value, network.value): chain for chain, network in CHAINS}
    selected: dict[Chain, dict[str, Any]] = {}
    for item in items:
        item_chain = item.get('chain')
        item_network = item.get('network')
        if not isinstance(item_chain, str) or not isinstance(item_network, str):
            raise RuntimeError('Gateway chain/network values are invalid.')
        key = (item_chain, item_network)
        chain = wanted.get(key)
        if chain is not None:
            selected[chain] = item
    if set(selected) != {chain for chain, _network in CHAINS}:
        raise RuntimeError('Gateway catalog does not contain every selected chain/network.')
    return selected


def _tip_call(chain: Chain, request_id: int) -> dict[str, object]:
    if chain in {Chain.ETHEREUM, Chain.POLYGON, Chain.BSC, Chain.ARBITRUM, Chain.OPTIMISM, Chain.BASE}:
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'eth_getBlockByNumber', 'params': ['latest', False]}
    if chain is Chain.SOLANA:
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'getSlot', 'params': [{'commitment': 'finalized'}]}
    if chain in {Chain.BITCOIN, Chain.LITECOIN}:
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'getblockcount', 'params': []}
    return {'jsonrpc': '2.0', 'id': request_id, 'method': 'eth_blockNumber', 'params': []}


def _redis_ttl_call(chain: Chain, request_id: int) -> dict[str, object]:
    if chain in {Chain.ETHEREUM, Chain.POLYGON, Chain.BSC, Chain.ARBITRUM, Chain.OPTIMISM, Chain.BASE, Chain.TRON}:
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'eth_blockNumber', 'params': []}
    if chain is Chain.SOLANA:
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'getSlot', 'params': [{'commitment': 'finalized'}]}
    return {'jsonrpc': '2.0', 'id': request_id, 'method': 'getblockchaininfo', 'params': []}


def _assert_success(response: httpx.Response) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f'Public request returned HTTP {response.status_code}: {response.text[:300]}')
    payload = response.json()
    if not isinstance(payload, dict) or 'result' not in payload:
        raise RuntimeError(f'Public JSON-RPC request failed: {payload!r}.')
    return payload


def _assert_jsonrpc_result(response: httpx.Response, request_id: int, expected_result: object) -> dict[str, Any]:
    payload = _assert_success(response)
    if payload.get('jsonrpc') != '2.0' or payload.get('id') != request_id or payload['result'] != expected_result:
        raise RuntimeError(
            f'Public JSON-RPC response mismatch for request {request_id}: expected {expected_result!r}, got {payload!r}.'
        )
    return payload


def _redis_ttl_result(chain: Chain) -> object:
    height = HEIGHTS[chain] - 1
    if chain in {Chain.ETHEREUM, Chain.POLYGON, Chain.BSC, Chain.ARBITRUM, Chain.OPTIMISM, Chain.BASE, Chain.TRON}:
        return hex(height)
    if chain is Chain.SOLANA:
        return height
    return {'blocks': height, 'headers': height, 'initialblockdownload': False}


def _cache_digest(method: str, identity: object) -> str:
    canonical = orjson.dumps({'method': method, 'identity': identity}, option=orjson.OPT_SORT_KEYS)
    return hashlib.blake2b(canonical, digest_size=20).hexdigest()


async def _create_app(client: GatewayClient, name: str) -> AccountResources:
    app = await client.create_app(name)
    gateways = _gateway_map(await client.list_gateways(app['id']))
    return AccountResources(
        app_id=app['id'],
        api_key=app['api_key'],
        gateways=gateways,
        endpoints=[],
        routes={},
    )


async def _create_admin_endpoints(
    client: GatewayClient,
    resources: AccountResources,
    mock_url: str,
    token: str,
) -> tuple[AdminEndpointMap, dict[str, EndpointResource]]:
    calls: list[tuple[Chain, str, int, Any]] = []
    for chain, network in CHAINS:
        calls.append(
            (
                chain,
                'bad',
                0,
                client.create_endpoint(
                    name=f'integration-{chain.value}-bad',
                    chain=chain.value,
                    network=network.value,
                    protocol='jsonrpc',
                    url=f'{mock_url}/run/{token}/jsonrpc/unavailable/{chain.value}/0',
                ),
            )
        )
        for source in range(3):
            calls.append(
                (
                    chain,
                    'good',
                    source,
                    client.create_endpoint(
                        name=f'integration-{chain.value}-good-{source}',
                        chain=chain.value,
                        network=network.value,
                        protocol='jsonrpc',
                        url=f'{mock_url}/run/{token}/jsonrpc/good/{chain.value}/{source}',
                    ),
                )
            )
    values = await asyncio.gather(*(call[3] for call in calls))
    bad_by_chain: dict[Chain, EndpointResource] = {}
    good_by_chain: dict[Chain, list[EndpointResource]] = {chain: [] for chain, _network in CHAINS}
    for (chain, kind, _source, _awaitable), endpoint in zip(calls, values, strict=True):
        resources.endpoints.append(endpoint)
        if kind == 'bad':
            bad_by_chain[chain] = endpoint
        else:
            good_by_chain[chain].append(endpoint)
    result: dict[Chain, tuple[EndpointResource, tuple[EndpointResource, EndpointResource, EndpointResource]]] = {}
    for chain, _network in CHAINS:
        bad = bad_by_chain.get(chain)
        good = good_by_chain[chain]
        if bad is None or len(good) != 3:
            raise RuntimeError(f'Endpoint creation mapping failed for {chain.value}.')
        result[chain] = (bad, (good[0], good[1], good[2]))

    extras: dict[str, EndpointResource] = {}
    ethereum_network = Network.MAINNET.value
    for behavior in ('invalid', 'timeout', 'wrong_height', 'trace_503', 'rate_limit', 'oversized'):
        endpoint = await client.create_endpoint(
            name=f'integration-ethereum-{behavior}',
            chain=Chain.ETHEREUM.value,
            network=ethereum_network,
            protocol='jsonrpc',
            url=f'{mock_url}/run/{token}/jsonrpc/{behavior}/ethereum/0',
        )
        resources.endpoints.append(endpoint)
        extras[behavior] = endpoint
    for behavior in ('unavailable', 'good', 'rate_limit_date'):
        endpoint = await client.create_endpoint(
            name=f'integration-tron-http-{behavior}',
            chain=Chain.TRON.value,
            network=Network.MAINNET.value,
            protocol='http_api',
            url=f'{mock_url}/run/{token}/http/{behavior}/tron',
        )
        resources.endpoints.append(endpoint)
        extras[f'http-{behavior}'] = endpoint
    return result, extras


async def execute_flow(
    *,
    api_url: str,
    peer_api_url: str,
    mock_url: str,
    redis_url: str,
    postgres_url: str,
    token: str,
) -> dict[str, object]:
    admin = GatewayClient(api_url)
    admin_peer = GatewayClient(peer_api_url)
    user = GatewayClient(api_url)
    user_peer = GatewayClient(peer_api_url)
    inspector = RuntimeInspector(redis_url, postgres_url)
    usage_auditor = UsageAuditor(redis_url, postgres_url)
    admin_resources: AccountResources | None = None
    user_resources: AccountResources | None = None
    admin_chains: dict[Chain, ChainResources] = {}
    user_http_endpoint: EndpointResource | None = None
    method_routes: list[tuple[str, RouteResource]] = []
    report: dict[str, object] = {}
    cleanup_errors: list[str] = []
    try:
        report['empty_baseline'] = await inspector.audit_empty_baseline()
        await admin.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        await admin_peer.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        await user.login(USER_EMAIL, USER_PASSWORD)
        await user_peer.login(USER_EMAIL, USER_PASSWORD)
        suffix = secrets.token_hex(5)
        admin_resources = await _create_app(admin, f'integration-admin-{suffix}')
        user_resources = await _create_app(user, f'integration-user-{suffix}')
        report['publisher_identity'] = await inspector.audit_admin_app(admin_resources.app_id)
        admin_endpoints, extras = await _create_admin_endpoints(admin, admin_resources, mock_url, token)

        user_endpoint_tasks = []
        user_order = []
        for chain, network in CHAINS:
            user_order.append(chain)
            user_endpoint_tasks.append(
                user.create_endpoint(
                    name=f'integration-user-{chain.value}',
                    chain=chain.value,
                    network=network.value,
                    protocol='jsonrpc',
                    url=f'{mock_url}/run/{token}/jsonrpc/good/{chain.value}/9',
                )
            )
        user_values = await asyncio.gather(*user_endpoint_tasks)
        user_resources.endpoints.extend(user_values)
        user_endpoints = dict(zip(user_order, user_values, strict=True))
        user_http_endpoint = await user.create_endpoint(
            name='integration-user-tron-http',
            chain='tron',
            network='mainnet',
            protocol='http_api',
            url=f'{mock_url}/run/{token}/http/good/tron',
        )
        user_resources.endpoints.append(user_http_endpoint)

        for chain, _network in CHAINS:
            gateway_id = admin_resources.gateways[chain]['id']
            route = await admin.get_jsonrpc_route(gateway_id)
            bad, good = admin_endpoints[chain]
            route = await admin.replace_jsonrpc_route(gateway_id, route, [bad.id, good[0].id])
            admin_resources.routes[chain] = route
            admin_chains[chain] = ChainResources(gateway=admin_resources.gateways[chain], route=route, bad=bad, good=good)

            user_gateway_id = user_resources.gateways[chain]['id']
            user_route = await user.get_jsonrpc_route(user_gateway_id)
            user_resources.routes[chain] = await user.replace_jsonrpc_route(
                user_gateway_id, user_route, [user_endpoints[chain].id], max_attempts=1
            )

        tron_gateway_id = admin_resources.gateways[Chain.TRON]['id']
        admin_http_route = await admin.get_http_route(tron_gateway_id)
        admin_resources.http_route = await admin.replace_http_route(
            tron_gateway_id,
            admin_http_route,
            [extras['http-unavailable'].id, extras['http-good'].id],
        )
        user_tron_gateway_id = user_resources.gateways[Chain.TRON]['id']
        user_http_route = await user.get_http_route(user_tron_gateway_id)
        user_resources.http_route = await user.replace_http_route(
            user_tron_gateway_id, user_http_route, [user_http_endpoint.id]
        )

        report['user_warmup'] = await _user_warmup(user, user_resources)
        tip_specs = await _seed_tips(admin, admin_resources, admin_chains)
        await _open_bad_circuits(admin, admin_resources, admin_chains)
        report['adaptive_circuit'] = await _adaptive_circuit_flow(
            admin,
            admin_resources,
            extras,
            mock_url,
            inspector,
        )
        await _clear_mock_counters(mock_url)
        report['tip_conflict'] = await _tip_conflict_burst(
            admin,
            admin_peer,
            admin_resources,
            admin_chains[Chain.ETHEREUM].good[0],
            mock_url,
            token,
            inspector,
        )
        runtime = await inspector.audit_runtime(
            tip_specs,
            [(value.bad.id, value.bad.version) for value in admin_chains.values()],
            [(endpoint.id, endpoint.version) for value in admin_chains.values() for endpoint in value.good],
        )
        report['runtime_state'] = runtime

        await inspector.clear_redis_ttl()
        await _clear_mock_counters(mock_url)
        singleflight_report, redis_ttl_specs = await _redis_ttl_singleflight(
            admin,
            admin_peer,
            user,
            admin_resources,
            user_resources,
            mock_url,
            inspector,
        )
        report['singleflight'] = singleflight_report
        await inspector.clear_redis_ttl()
        await _clear_mock_counters(mock_url)
        report['publisher_soak'] = await _publisher_soak(admin, admin_peer, admin_resources, mock_url, inspector)
        await inspector.audit_cache_flights()
        await _clear_mock_counters(mock_url)
        expected_postgres_retention, hash_redis_ttl_specs, retention_loads = await _postgres_retention_cache_calls(
            admin, admin_resources, mock_url
        )
        cache_report = await inspector.audit_cache(expected_postgres_retention, [*redis_ttl_specs, *hash_redis_ttl_specs])
        cache_report['upstream'] = retention_loads
        report['system_cache'] = cache_report
        report['negative'] = await _negative_calls(
            admin,
            admin_resources,
            extras,
            method_routes,
            mock_url,
            admin_chains[Chain.ETHEREUM].good[0].id,
            inspector,
        )
        report['burst'] = await _burst_rounds(admin, admin_resources, rounds=5, concurrency_per_chain=10)
        report['admission'] = await _admission_calls(admin, admin_resources)
        report['usage'] = await _usage_qualification(
            admin,
            admin_peer,
            user,
            user_peer,
            admin_resources,
            user_resources,
            mock_url,
            inspector,
            usage_auditor,
        )
        report['success'] = True
        return report
    finally:
        if admin_resources is not None:
            await _cleanup_account(admin, admin_resources, method_routes, cleanup_errors)
        if user_resources is not None:
            await _cleanup_account(user, user_resources, [], cleanup_errors)
        try:
            await admin.logout()
        except Exception as exc:
            cleanup_errors.append(f'Admin logout failed: {exc!r}')
        try:
            await admin_peer.logout()
        except Exception as exc:
            cleanup_errors.append(f'Peer Admin logout failed: {exc!r}')
        try:
            await user.logout()
        except Exception as exc:
            cleanup_errors.append(f'User logout failed: {exc!r}')
        try:
            await user_peer.logout()
        except Exception as exc:
            cleanup_errors.append(f'Peer User logout failed: {exc!r}')
        await inspector.close()
        await usage_auditor.close()
        await admin.close()
        await admin_peer.close()
        await user.close()
        await user_peer.close()
        report['cleanup_errors'] = cleanup_errors
        if cleanup_errors:
            raise RuntimeError('; '.join(cleanup_errors))


async def _user_warmup(client: GatewayClient, resources: AccountResources) -> dict[str, int]:
    responses = await asyncio.gather(
        *(
            client.jsonrpc(
                resources.gateways[chain],
                resources.api_key,
                {
                    'jsonrpc': '2.0',
                    'id': 900,
                    'method': f'integration_user_warmup_{chain.value}',
                    'params': [],
                },
            )
            for chain, _network in CHAINS
        )
    )
    for response in responses:
        _assert_success(response)
    tron = await client.http_api(resources.gateways[Chain.TRON], resources.api_key, 'GET', 'wallet/getnowblock')
    if tron.status_code != 200 or tron.json().get('block_header', {}).get('raw_data', {}).get('number') != HEIGHTS[Chain.TRON]:
        raise RuntimeError('TRON HTTP API warmup failed.')
    return {'jsonrpc': len(responses), 'http_api': 1}


async def _seed_tips(
    client: GatewayClient,
    resources: AccountResources,
    chains: dict[Chain, ChainResources],
) -> list[TipAuditSpec]:
    async def seed(chain: Chain, value: ChainResources) -> TipAuditSpec:
        gateway_id = value.gateway['id']
        route = resources.routes[chain]
        for source, endpoint in enumerate(value.good):
            route = await client.replace_jsonrpc_route(gateway_id, route, [endpoint.id], max_attempts=1)
            response = await client.jsonrpc(value.gateway, resources.api_key, _tip_call(chain, 1000 + source))
            _assert_success(response)
            if chain in {Chain.SOLANA, Chain.TRON} and source < 2:
                await asyncio.sleep(5.4)
        route = await client.replace_jsonrpc_route(gateway_id, route, [value.bad.id, value.good[0].id])
        resources.routes[chain] = route
        value.route = route
        if chain is Chain.SOLANA:
            unit, finality = TipUnit.SLOT, Finality.FINALIZED
        else:
            unit, finality = TipUnit.BLOCK, Finality.LATEST
        return TipAuditSpec(
            chain=chain,
            network=next(network for item, network in CHAINS if item is chain),
            unit=unit,
            finality=finality,
            endpoint_ids=(value.good[0].id, value.good[1].id, value.good[2].id),
            endpoint_values=(HEIGHTS[chain] - 1, HEIGHTS[chain], HEIGHTS[chain] + 1),
            expected_value=HEIGHTS[chain],
        )

    return list(await asyncio.gather(*(seed(chain, value) for chain, value in chains.items())))


async def _open_bad_circuits(
    client: GatewayClient,
    resources: AccountResources,
    chains: dict[Chain, ChainResources],
) -> None:
    async def fail(chain: Chain, value: ChainResources) -> None:
        for offset in range(24):
            payload = {'jsonrpc': '2.0', 'id': 2000 + offset, 'method': f'integration_failure_{offset}', 'params': []}
            _assert_success(await client.jsonrpc(value.gateway, resources.api_key, payload))
            if offset == 19:
                await asyncio.sleep(0.1)

    await asyncio.gather(*(fail(chain, value) for chain, value in chains.items()))


async def _adaptive_circuit_flow(
    client: GatewayClient,
    resources: AccountResources,
    extras: dict[str, EndpointResource],
    mock_url: str,
    inspector: RuntimeInspector,
) -> dict[str, object]:
    gateway = resources.gateways[Chain.ETHEREUM]
    gateway_id = gateway['id']
    route = await client.create_method_route(
        gateway_id,
        ['debug_traceTransaction', 'integration_circuit_standard'],
        extras['trace_503'].id,
    )
    await _clear_mock_counters(mock_url)
    trace_codes: list[int | None] = []
    try:
        for offset in range(24):
            response = await client.jsonrpc(
                gateway,
                resources.api_key,
                {
                    'jsonrpc': '2.0',
                    'id': 2300 + offset,
                    'method': 'debug_traceTransaction',
                    'params': [f'0x{offset:064x}'],
                },
            )
            payload = response.json()
            error = payload.get('error') if isinstance(payload, dict) else None
            trace_codes.append(error.get('code') if isinstance(error, dict) else None)
            if offset == 19:
                await asyncio.sleep(0.1)
        standard = await client.jsonrpc(
            gateway,
            resources.api_key,
            {'jsonrpc': '2.0', 'id': 2399, 'method': 'integration_circuit_standard', 'params': []},
        )
        standard_payload = _assert_success(standard)
        counters = await _mock_counters(mock_url)
        trace_upstream = counters.get('jsonrpc:trace_503:ethereum:0:debug_traceTransaction', 0)
        standard_upstream = counters.get('jsonrpc:trace_503:ethereum:0:integration_circuit_standard', 0)
        if -32005 not in trace_codes or -32004 not in trace_codes:
            raise RuntimeError(f'Adaptive Circuit did not expose attempted and open failures: {trace_codes!r}.')
        if trace_upstream >= len(trace_codes):
            raise RuntimeError('Trace Circuit did not stop upstream requests after opening.')
        if standard_upstream != 1:
            raise RuntimeError('Standard workload did not remain isolated from the trace Circuit.')

        rate_health_before = await inspector.endpoint_health(extras['rate_limit'].id, extras['rate_limit'].version)
        rate_route = await client.create_method_route(gateway_id, ['integration_rate_limit'], extras['rate_limit'].id)
        try:
            rate_codes: list[int | None] = []
            for request_id in (2400, 2401):
                response = await client.jsonrpc(
                    gateway,
                    resources.api_key,
                    {'jsonrpc': '2.0', 'id': request_id, 'method': 'integration_rate_limit', 'params': []},
                )
                payload = response.json()
                error = payload.get('error') if isinstance(payload, dict) else None
                rate_codes.append(error.get('code') if isinstance(error, dict) else None)
            await asyncio.sleep(1.1)
            response = await client.jsonrpc(
                gateway,
                resources.api_key,
                {'jsonrpc': '2.0', 'id': 2402, 'method': 'integration_rate_limit', 'params': []},
            )
            payload = response.json()
            error = payload.get('error') if isinstance(payload, dict) else None
            rate_codes.append(error.get('code') if isinstance(error, dict) else None)
            if rate_codes != [-32099, -32004, -32099]:
                raise RuntimeError(f'Rate-limit Circuit cooldown was not enforced: {rate_codes!r}.')
            rate_counters = await _mock_counters(mock_url)
            rate_upstream = rate_counters.get('jsonrpc:rate_limit:ethereum:0:integration_rate_limit', 0)
            if rate_upstream != 2:
                raise RuntimeError(f'Rate-limit Circuit did not suppress the immediate retry: {rate_upstream}.')
            rate_health = await inspector.endpoint_health(extras['rate_limit'].id, extras['rate_limit'].version)
            if rate_health != rate_health_before:
                raise RuntimeError(
                    f'Rate-limited JSON-RPC response polluted Endpoint Health: before={rate_health_before!r}, '
                    f'after={rate_health!r}.'
                )
        finally:
            await client.delete_method_route(gateway_id, rate_route)

        tron_gateway = resources.gateways[Chain.TRON]
        if resources.http_route is None:
            raise RuntimeError('TRON HTTP API route is unavailable for Circuit qualification.')
        date_route = await client.replace_http_route(
            tron_gateway['id'],
            resources.http_route,
            [extras['http-rate_limit_date'].id],
        )
        try:
            date_response = await client.http_api(tron_gateway, resources.api_key, 'GET', 'wallet/getnowblock')
            if date_response.status_code != 429:
                raise RuntimeError(f'HTTP-date rate-limit response was not preserved: {date_response.status_code}.')
            date_circuit = await inspector.circuit_snapshot(
                extras['http-rate_limit_date'].id,
                extras['http-rate_limit_date'].version,
            )
            if date_circuit.opened_at is None or date_circuit.retry_at is None:
                raise RuntimeError(f'HTTP-date throttle did not open Circuit: {date_circuit!r}.')
            date_retry_seconds = (date_circuit.retry_at - date_circuit.opened_at).total_seconds()
            if not 3 <= date_retry_seconds <= 5:
                raise RuntimeError(f'HTTP-date Retry-After was not applied: {date_retry_seconds}.')
        finally:
            resources.http_route = await client.replace_http_route(
                tron_gateway['id'],
                date_route,
                [extras['http-unavailable'].id, extras['http-good'].id],
            )

        oversized_route = await client.create_method_route(
            gateway_id,
            ['integration_oversized'],
            extras['oversized'].id,
        )
        try:
            oversized_codes: list[int | None] = []
            oversized_lengths: list[int] = []
            for offset in range(6):
                response = await client.jsonrpc(
                    gateway,
                    resources.api_key,
                    {'jsonrpc': '2.0', 'id': 2450 + offset, 'method': 'integration_oversized', 'params': []},
                )
                payload = response.json()
                error = payload.get('error') if isinstance(payload, dict) else None
                result = payload.get('result') if isinstance(payload, dict) else None
                oversized_codes.append(error.get('code') if isinstance(error, dict) else None)
                oversized_lengths.append(len(result) if isinstance(result, str) else -1)
            counters = await _mock_counters(mock_url)
            oversized_upstream = counters.get('jsonrpc:oversized:ethereum:0:integration_oversized', 0)
            expected_length = 8 * 1024 * 1024 + 1024
            if oversized_codes != [None] * 6 or oversized_lengths != [expected_length] * 6 or oversized_upstream != 6:
                raise RuntimeError(
                    'Large responses were not forwarded intact: '
                    f'codes={oversized_codes!r}, lengths={oversized_lengths!r}, upstream={oversized_upstream}.'
                )
        finally:
            await client.delete_method_route(gateway_id, oversized_route)

        return {
            'trace_codes': trace_codes,
            'trace_upstream': trace_upstream,
            'standard_upstream': standard_upstream,
            'standard_result': standard_payload['result'],
            'rate_limit_codes': rate_codes,
            'rate_limit_upstream': rate_upstream,
            'http_date_retry_seconds': date_retry_seconds,
            'oversized_codes': oversized_codes,
            'oversized_lengths': oversized_lengths,
            'oversized_upstream': oversized_upstream,
        }
    finally:
        await client.delete_method_route(gateway_id, route)


async def _tip_conflict_burst(
    admin: GatewayClient,
    admin_peer: GatewayClient,
    resources: AccountResources,
    endpoint: EndpointResource,
    mock_url: str,
    token: str,
    inspector: RuntimeInspector,
) -> dict[str, object]:
    low_call = {'jsonrpc': '2.0', 'id': 2500, 'method': 'eth_getBlockByNumber', 'params': ['latest', False]}
    high_call = low_call | {'id': 2501}
    restore_call = low_call | {'id': 2502}
    low_height = HEIGHTS[Chain.ETHEREUM] - 1
    high_height = HEIGHTS[Chain.ETHEREUM] + 1
    low_result = {'number': hex(low_height), 'hash': f'0x{low_height:064x}', 'source': 0}
    high_result = {'number': hex(high_height), 'hash': f'0x{high_height:064x}', 'source': 2}

    await _clear_mock_ledger(mock_url)
    await _arm_mock_barrier(mock_url, 'tip-low')
    barrier_url = f'{mock_url}/run/{token}/jsonrpc/barrier_low/ethereum/0'
    updated = await admin.update_endpoint_url(endpoint, barrier_url)
    endpoint.version = updated.version
    low_task = asyncio.create_task(admin.jsonrpc(resources.gateways[Chain.ETHEREUM], resources.api_key, low_call))
    try:
        await _wait_mock_barrier(mock_url, 'tip-low', expected_waiters=1)
        high_url = f'{mock_url}/run/{token}/jsonrpc/good/ethereum/2'
        updated = await admin.update_endpoint_url(endpoint, high_url)
        endpoint.version = updated.version
        high_response = await admin_peer.jsonrpc(resources.gateways[Chain.ETHEREUM], resources.api_key, high_call)
        _assert_jsonrpc_result(high_response, 2501, high_result)
        high_tip = await inspector.wait_endpoint_tip(
            endpoint_id=endpoint.id,
            endpoint_version=endpoint.version,
            expected_value=high_height,
        )
    finally:
        await _release_mock_barrier(mock_url, 'tip-low')
        low_response = await low_task
    _assert_jsonrpc_result(low_response, 2500, low_result)
    await asyncio.sleep(0.5)
    winning_tip = await inspector.wait_endpoint_tip(
        endpoint_id=endpoint.id,
        endpoint_version=endpoint.version,
        expected_value=high_height,
    )
    if winning_tip != high_tip:
        raise RuntimeError(f'Late old Tip revision replaced or mutated the stored winner: {winning_tip!r}.')
    restore_url = f'{mock_url}/run/{token}/jsonrpc/good/ethereum/0'
    updated = await admin.update_endpoint_url(endpoint, restore_url)
    endpoint.version = updated.version
    restore_response = await admin.jsonrpc(resources.gateways[Chain.ETHEREUM], resources.api_key, restore_call)
    _assert_jsonrpc_result(restore_response, 2502, low_result)
    restored_tip = await inspector.wait_endpoint_tip(
        endpoint_id=endpoint.id,
        endpoint_version=endpoint.version,
        expected_value=low_height,
    )

    peer_counts, replica_ips = await _audit_mock_peers(mock_url)
    expectations = [
        jsonrpc_expectation(
            started_sequence=1,
            finished_sequence=4,
            replica='api-a',
            behavior='barrier_low',
            chain='ethereum',
            source=0,
            request=low_call,
            result=low_result,
        ),
        jsonrpc_expectation(
            started_sequence=2,
            finished_sequence=3,
            replica='api-b',
            behavior='good',
            chain='ethereum',
            source=2,
            request=high_call,
            result=high_result,
        ),
        jsonrpc_expectation(
            started_sequence=5,
            finished_sequence=6,
            replica='api-a',
            behavior='good',
            chain='ethereum',
            source=0,
            request=restore_call,
            result=low_result,
        ),
    ]
    ledger = await _audit_mock_ledger(mock_url, expectations, replica_ips)
    return {
        'requests': 3,
        'semantic_responses_verified': 3,
        'endpoint_tip_dimension': 'ethereum/mainnet/block/latest',
        'high_revision_before_release': high_tip,
        'winning_revision_after_late_low': winning_tip,
        'restored_revision': restored_tip,
        'api_replica_peers': peer_counts,
        'ledger': ledger,
    }


async def _burst_rounds(
    client: GatewayClient,
    resources: AccountResources,
    *,
    rounds: int,
    concurrency_per_chain: int,
) -> dict[str, int]:
    completed = 0
    for round_number in range(rounds):
        gate = asyncio.Event()

        async def json_call(
            chain: Chain,
            chain_index: int,
            offset: int,
            start: asyncio.Event,
            burst_round: int,
        ) -> None:
            await start.wait()
            request_id = 10_000 + burst_round * 1000 + chain_index * 100 + offset
            method = f'integration_burst_{chain.value}_{burst_round}_{offset}'
            params = [chain.value]
            payload = {
                'jsonrpc': '2.0',
                'id': request_id,
                'method': method,
                'params': params,
            }
            response = await client.jsonrpc(resources.gateways[chain], resources.api_key, payload)
            expected_result = {'chain': chain.value, 'source': 0, 'method': method, 'params': params}
            _assert_jsonrpc_result(response, request_id, expected_result)

        async def http_call(offset: int, start: asyncio.Event, burst_round: int) -> None:
            await start.wait()
            path = f'v1/accounts/integration-{burst_round}-{offset}'
            response = await client.http_api(resources.gateways[Chain.TRON], resources.api_key, 'GET', path)
            expected_payload = {'Success': True, 'path': path, 'source': 'mock'}
            if response.status_code != 200 or response.json() != expected_payload:
                raise RuntimeError(f'TRON burst response mismatch: {response.status_code} {response.text[:300]}')

        tasks = [
            asyncio.create_task(json_call(chain, chain_index, offset, gate, round_number))
            for chain_index, (chain, _network) in enumerate(CHAINS)
            for offset in range(concurrency_per_chain)
        ]
        tasks.extend(asyncio.create_task(http_call(offset, gate, round_number)) for offset in range(concurrency_per_chain))
        gate.set()
        async with asyncio.timeout(30):
            await asyncio.gather(*tasks)
        completed += len(tasks)
    return {'rounds': rounds, 'requests': completed, 'semantic_responses_verified': completed}


async def _usage_qualification(
    admin: GatewayClient,
    admin_peer: GatewayClient,
    user: GatewayClient,
    user_peer: GatewayClient,
    admin_resources: AccountResources,
    user_resources: AccountResources,
    mock_url: str,
    inspector: RuntimeInspector,
    auditor: UsageAuditor,
) -> dict[str, object]:
    admin_account_id, admin_app_id = await auditor.load_app_identity(admin_resources.app_id)
    user_account_id, user_app_id = await auditor.load_app_identity(user_resources.app_id)
    reset = await auditor.reset()
    await _clear_mock_counters(mock_url)
    specs, traffic = await _usage_rounds(
        (
            ('admin_a', admin, admin_resources, admin_account_id),
            ('admin_b', admin_peer, admin_resources, admin_account_id),
            ('user_a', user, user_resources, user_account_id),
            ('user_b', user_peer, user_resources, user_account_id),
        ),
        rounds=6,
    )
    await inspector.clear_redis_ttl()
    cache_specs, cache = await _usage_cache_calls(
        admin,
        admin_peer,
        user,
        admin_resources,
        user_resources,
        admin_account_id,
        user_account_id,
        mock_url,
    )
    specs.extend(cache_specs)
    await inspector.audit_cache_flights()
    peer_counts, _replica_ips = await _audit_mock_peers(mock_url)
    events, stream = await auditor.audit_stream(specs)
    drain = await auditor.drain(len(events))
    database = await auditor.audit_database(events)
    api = await auditor.audit_api(
        [
            (admin, admin_account_id, admin_app_id, user_app_id),
            (user, user_account_id, user_app_id, admin_app_id),
        ],
        events,
    )
    return {
        'reset': reset,
        'traffic': traffic,
        'cache': cache,
        'api_replica_peers': peer_counts,
        'stream': stream,
        'drain': drain,
        'database': database,
        'api': api,
    }


async def _usage_cache_calls(
    admin: GatewayClient,
    admin_peer: GatewayClient,
    user: GatewayClient,
    admin_resources: AccountResources,
    user_resources: AccountResources,
    admin_account_id: str,
    user_account_id: str,
    mock_url: str,
) -> tuple[list[UsageCallSpec], dict[str, int]]:
    specs: list[UsageCallSpec] = []
    for chain_index, (chain, network) in enumerate(CHAINS):
        method = str(_redis_ttl_call(chain, 1)['method'])
        expected_result = _redis_ttl_result(chain)
        request_base = 30_000 + chain_index * 10
        admin_key = f'jsonrpc:good:{chain.value}:0:{method}'
        leader_task = asyncio.create_task(
            admin.jsonrpc(
                admin_resources.gateways[chain],
                admin_resources.api_key,
                _redis_ttl_call(chain, request_base),
            )
        )
        await _wait_mock_counter(mock_url, admin_key)
        follower_task = asyncio.create_task(
            admin_peer.jsonrpc(
                admin_resources.gateways[chain],
                admin_resources.api_key,
                _redis_ttl_call(chain, request_base + 1),
            )
        )
        leader_response, follower_response = await asyncio.gather(leader_task, follower_task)
        user_response = await user.jsonrpc(
            user_resources.gateways[chain],
            user_resources.api_key,
            _redis_ttl_call(chain, request_base + 2),
        )
        actors = (
            (leader_response, admin_resources, admin_account_id, False),
            (follower_response, admin_resources, admin_account_id, True),
            (user_response, user_resources, user_account_id, True),
        )
        for actor_index, (response, resources, account_id, cache_hit) in enumerate(actors):
            request_id = request_base + actor_index
            _assert_jsonrpc_result(response, request_id, expected_result)
            actual_header = response.headers.get(CACHE_HEADER)
            expected_header = 'HIT' if cache_hit else None
            if actual_header != expected_header:
                raise RuntimeError(
                    f'Cache header mismatch for {chain.value} request {request_id}: '
                    f'expected {expected_header!r}, got {actual_header!r}.'
                )
            specs.append(
                UsageCallSpec(
                    account_id=account_id,
                    app_id=resources.app_id,
                    gateway_id=resources.gateways[chain]['id'],
                    chain=chain,
                    network=network,
                    method=method,
                    successful=True,
                    cache_eligible=True,
                    cache_hit=cache_hit,
                )
            )
        counters = await _mock_counters(mock_url)
        if counters.get(admin_key) != 1:
            raise RuntimeError(f'Usage single-flight issued more than one upstream request for {chain.value}: {counters!r}.')
    return specs, {
        'requests': len(specs),
        'chains': len(CHAINS),
        'expected_misses': len(CHAINS),
        'expected_hits': len(CHAINS) * 2,
    }


async def _usage_rounds(
    actors: tuple[tuple[str, GatewayClient, AccountResources, str], ...],
    *,
    rounds: int,
) -> tuple[list[UsageCallSpec], dict[str, int]]:
    started_at = time.monotonic()
    specs: list[UsageCallSpec] = []
    successful = 0
    failed = 0
    for round_number in range(rounds):
        gate = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []
        for actor_index, (actor, client, resources, account_id) in enumerate(actors):
            for chain_index, (chain, network) in enumerate(CHAINS):
                is_failure = (round_number + actor_index + chain_index) % 3 == 0
                outcome = 'failure' if is_failure else 'success'
                method = f'integration_usage_{outcome}_{actor}_{chain.value}_{round_number}'
                request_id = 20_000 + round_number * 1000 + actor_index * 100 + chain_index
                params = [actor, chain.value, round_number]
                expected_source = 9 if actor.startswith('user_') else 0
                spec = UsageCallSpec(
                    account_id=account_id,
                    app_id=resources.app_id,
                    gateway_id=resources.gateways[chain]['id'],
                    chain=chain,
                    network=network,
                    method=method,
                    successful=not is_failure,
                )
                specs.append(spec)

                async def call(
                    call_client: GatewayClient = client,
                    call_resources: AccountResources = resources,
                    call_spec: UsageCallSpec = spec,
                    call_id: int = request_id,
                    call_params: list[str | int] = params,
                    call_source: int = expected_source,
                    start: asyncio.Event = gate,
                ) -> None:
                    await start.wait()
                    response = await call_client.jsonrpc(
                        call_resources.gateways[call_spec.chain],
                        call_resources.api_key,
                        {
                            'jsonrpc': '2.0',
                            'id': call_id,
                            'method': call_spec.method,
                            'params': call_params,
                        },
                    )
                    if call_spec.successful:
                        expected_result = {
                            'chain': call_spec.chain.value,
                            'source': call_source,
                            'method': call_spec.method,
                            'params': call_params,
                        }
                        _assert_jsonrpc_result(response, call_id, expected_result)
                        return
                    payload = response.json()
                    if response.status_code != 200 or payload.get('error', {}).get('code') != -32602:
                        raise RuntimeError(f'Usage failure response mismatch for {call_spec.method}: {payload!r}.')

                tasks.append(asyncio.create_task(call()))
                if is_failure:
                    failed += 1
                else:
                    successful += 1
        gate.set()
        async with asyncio.timeout(30):
            await asyncio.gather(*tasks)
        await asyncio.sleep(0.05)
    return specs, {
        'rounds': rounds,
        'requests': len(specs),
        'successful': successful,
        'failed': failed,
        'chains': len(CHAINS),
        'actors': len(actors),
        'elapsed_ms': round((time.monotonic() - started_at) * 1000),
    }


async def _clear_mock_counters(mock_url: str) -> None:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.delete('/__integration/counters')
        response.raise_for_status()


async def _mock_counters(mock_url: str) -> dict[str, int]:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.get('/__integration/counters')
        response.raise_for_status()
        payload = response.json()
        return {str(key): int(value) for key, value in payload.items()}


async def _audit_mock_peers(mock_url: str) -> tuple[dict[str, int], dict[str, str]]:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.get('/__integration/peers')
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError('Mock peer report is invalid.')
    observed_raw = payload.get('observed')
    replicas_raw = payload.get('replicas')
    if not isinstance(observed_raw, dict) or not isinstance(replicas_raw, dict):
        raise RuntimeError('Mock peer report has no observed or replica mapping.')
    observed = {str(key): int(value) for key, value in observed_raw.items()}
    replica_ips: dict[str, str] = {}
    for replica in ('api-a', 'api-b'):
        values = replicas_raw.get(replica)
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
            raise RuntimeError(f'Mock DNS mapping for {replica} is not one exact address: {values!r}.')
        replica_ips[replica] = values[0]
    if len(set(replica_ips.values())) != 2:
        raise RuntimeError(f'Mock API replica addresses are not distinct: {replica_ips!r}.')
    if set(observed) != set(replica_ips.values()) or any(value <= 0 for value in observed.values()):
        raise RuntimeError(f'Mock peers do not match the two API replicas: observed={observed!r}, replicas={replica_ips!r}.')
    counts = {replica: observed[address] for replica, address in replica_ips.items()}
    return counts, replica_ips


async def _clear_mock_ledger(mock_url: str) -> None:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.delete('/__integration/ledger')
        response.raise_for_status()
        if response.json() != {'cleared': True}:
            raise RuntimeError(f'Mock ledger did not clear: {response.text[:300]}')


async def _audit_mock_ledger(
    mock_url: str,
    expectations: list[LedgerExpectation],
    replica_ips: dict[str, str],
) -> dict[str, object]:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.get('/__integration/ledger')
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or payload.get('active') != 0:
        raise RuntimeError(f'Mock ledger is invalid or has active requests: {payload!r}.')
    entries = payload.get('entries')
    if not isinstance(entries, list) or len(entries) != len(expectations):
        raise RuntimeError(f'Mock ledger cardinality mismatch: expected {len(expectations)}, got {entries!r}.')
    expected_keys = {
        'started_sequence',
        'finished_sequence',
        'peer',
        'transport',
        'behavior',
        'chain',
        'source',
        'method',
        'request_id',
        'request_digest',
        'params_digest',
        'status_code',
        'response_digest',
        'elapsed_ms',
    }
    for entry, expected in zip(entries, expectations, strict=True):
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            raise RuntimeError(f'Mock ledger entry shape mismatch: {entry!r}.')
        expected_entry = {
            'started_sequence': expected.started_sequence,
            'finished_sequence': expected.finished_sequence,
            'peer': replica_ips[expected.replica],
            'transport': 'jsonrpc',
            'behavior': expected.behavior,
            'chain': expected.chain,
            'source': expected.source,
            'method': expected.method,
            'request_id': expected.request_id,
            'request_digest': expected.request_digest,
            'params_digest': expected.params_digest,
            'status_code': expected.status_code,
            'response_digest': expected.response_digest,
        }
        actual_entry = {key: entry.get(key) for key in expected_entry}
        elapsed_ms = entry.get('elapsed_ms')
        if actual_entry != expected_entry or not isinstance(elapsed_ms, int | float) or elapsed_ms < 0:
            raise RuntimeError(f'Mock ledger mismatch: expected {expected_entry!r}, got {entry!r}.')
    next_sequence = len(expectations) * 2 + 1
    if payload.get('next_event_sequence') != next_sequence:
        raise RuntimeError(f'Mock ledger event sequence is incomplete: {payload!r}.')
    return {
        'entries': len(entries),
        'request_digests_verified': len(entries),
        'response_digests_verified': len(entries),
        'params_digests_verified': len(entries),
        'event_sequence_verified': True,
    }


async def _arm_mock_barrier(mock_url: str, name: str) -> None:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.put(f'/__integration/barriers/{name}')
        response.raise_for_status()


async def _release_mock_barrier(mock_url: str, name: str) -> None:
    async with httpx.AsyncClient(base_url=mock_url) as client:
        response = await client.post(f'/__integration/barriers/{name}/release')
        response.raise_for_status()


async def _wait_mock_barrier(mock_url: str, name: str, *, expected_waiters: int, timeout_seconds: float = 5) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    async with httpx.AsyncClient(base_url=mock_url) as client:
        while True:
            response = await client.get(f'/__integration/barriers/{name}')
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get('waiters') == expected_waiters and payload.get('released') is False:
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f'Mock barrier did not reach {expected_waiters} waiters: {payload!r}.')
            await asyncio.sleep(0.01)


async def _wait_mock_counter(mock_url: str, key: str, *, timeout_seconds: float = 2) -> None:
    await _wait_mock_counters(mock_url, {key: 1}, timeout_seconds=timeout_seconds)


async def _wait_mock_counters(
    mock_url: str,
    expected: dict[str, int],
    *,
    timeout_seconds: float = 2,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        counters = await _mock_counters(mock_url)
        if all(counters.get(key, 0) == count for key, count in expected.items()):
            return
        exceeded = {key: counters.get(key, 0) for key, count in expected.items() if counters.get(key, 0) > count}
        if exceeded:
            raise RuntimeError(f'Mock counters exceeded the leader barrier: {exceeded!r}.')
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f'Mock counters did not reach the leader barrier: {expected!r}.')
        await asyncio.sleep(0.01)


async def _redis_ttl_singleflight(
    admin: GatewayClient,
    admin_peer: GatewayClient,
    user: GatewayClient,
    admin_resources: AccountResources,
    user_resources: AccountResources,
    mock_url: str,
    inspector: RuntimeInspector,
) -> tuple[dict[str, object], list[RedisTtlAuditSpec]]:
    responses = []
    user_responses = []
    specs: list[RedisTtlAuditSpec] = []
    for chain_index, (chain, _network) in enumerate(CHAINS):
        method = str(_redis_ttl_call(chain, 1)['method'])
        admin_key = f'jsonrpc:good:{chain.value}:0:{method}'
        leader = admin if chain_index % 2 == 0 else admin_peer
        leader_task = asyncio.create_task(
            leader.jsonrpc(admin_resources.gateways[chain], admin_resources.api_key, _redis_ttl_call(chain, 3000))
        )
        await _wait_mock_counter(mock_url, admin_key)
        follower_tasks = [
            asyncio.create_task(
                (admin if offset % 2 == 0 else admin_peer).jsonrpc(
                    admin_resources.gateways[chain],
                    admin_resources.api_key,
                    _redis_ttl_call(chain, 3000 + offset),
                )
            )
            for offset in range(1, 10)
        ]
        await asyncio.sleep(0.05)
        if any(task.done() for task in follower_tasks):
            raise RuntimeError(f'Single-flight followers completed before the leader for {chain.value}.')
        await inspector.audit_cache_flight_count(1)
        follower_responses = await asyncio.gather(*follower_tasks)
        chain_responses = [await leader_task, *follower_responses]
        await inspector.audit_cache_flight_count(0)
        expected_result = _redis_ttl_result(chain)
        for offset, response in enumerate(chain_responses):
            _assert_jsonrpc_result(response, 3000 + offset, expected_result)
            expected_header = None if offset == 0 else 'HIT'
            actual_header = response.headers.get(CACHE_HEADER)
            if actual_header != expected_header:
                raise RuntimeError(
                    f'Single-flight cache header mismatch for {chain.value} request {3000 + offset}: '
                    f'expected {expected_header!r}, got {actual_header!r}.'
                )
        responses.extend(chain_responses)
        user_response = await user.jsonrpc(user_resources.gateways[chain], user_resources.api_key, _redis_ttl_call(chain, 4000))
        _assert_jsonrpc_result(user_response, 4000, expected_result)
        if user_response.headers.get(CACHE_HEADER) != 'HIT':
            raise RuntimeError(f'Warm user cache response did not report HIT for {chain.value}.')
        user_responses.append(user_response)
        specs.append(
            RedisTtlAuditSpec(
                chain=chain,
                network=next(network for item, network in CHAINS if item is chain),
                method=method,
                expected_cache_key=_cache_digest(method, 'finalized'),
                expected_result=expected_result,
            )
        )
    counters = await _mock_counters(mock_url)
    peer_counts, _replica_ips = await _audit_mock_peers(mock_url)
    for chain, _network in CHAINS:
        method = _redis_ttl_call(chain, 1)['method']
        admin_key = f'jsonrpc:good:{chain.value}:0:{method}'
        user_key = f'jsonrpc:good:{chain.value}:9:{method}'
        if counters.get(admin_key) != 1 or counters.get(user_key, 0) != 0:
            raise RuntimeError(f'Distributed single-flight invariant failed for {chain.value}: {counters!r}.')
    return (
        {
            'requests': len(responses),
            'admin_loads': 10,
            'admin_cache_hits': len(responses) - len(CHAINS),
            'user_cache_hits': len(user_responses),
            'api_replica_peers': peer_counts,
        },
        specs,
    )


async def _postgres_retention_cache_calls(
    client: GatewayClient,
    resources: AccountResources,
    mock_url: str,
) -> tuple[list[PostgresRetentionAuditSpec], list[RedisTtlAuditSpec], dict[str, object]]:
    retention_specs: list[PostgresRetentionAuditSpec] = []
    redis_ttl_specs: list[RedisTtlAuditSpec] = []
    expected_counters: dict[str, int] = {}
    for chain, network in CHAINS:
        height = HEIGHTS[chain] - 10
        if chain in {Chain.ETHEREUM, Chain.POLYGON, Chain.BSC, Chain.ARBITRUM, Chain.OPTIMISM, Chain.BASE}:
            method = 'eth_getBlockByNumber'
            payload = {'jsonrpc': '2.0', 'id': 5000, 'method': method, 'params': [hex(height), False]}
            expected_result: object = {
                'number': hex(height),
                'hash': f'0x{height:064x}',
                'source': 0,
            }
            identity: object = [hex(height), False]
        elif chain is Chain.SOLANA:
            method = 'getBlock'
            payload = {
                'jsonrpc': '2.0',
                'id': 5000,
                'method': method,
                'params': [height, {'encoding': 'json', 'commitment': 'finalized', 'rewards': False}],
            }
            expected_result = {'blockHeight': height - 1, 'blockTime': 1_700_000_000, 'source': 0}
            identity = [
                height,
                {
                    'encoding': 'json',
                    'commitment': 'finalized',
                    'rewards': False,
                    'maxSupportedTransactionVersion': 0,
                },
            ]
        elif chain in {Chain.BITCOIN, Chain.LITECOIN}:
            hash_call = {'jsonrpc': '2.0', 'id': 5000, 'method': 'getblockhash', 'params': [height]}
            expected_hash = f'{height:064x}'
            hash_response = await client.jsonrpc(resources.gateways[chain], resources.api_key, hash_call)
            hash_payload = _assert_jsonrpc_result(hash_response, 5000, expected_hash)
            block_hash = hash_payload['result']
            redis_ttl_specs.append(
                RedisTtlAuditSpec(
                    chain=chain,
                    network=network,
                    method='getblockhash',
                    expected_cache_key=_cache_digest('getblockhash', height),
                    expected_result=expected_hash,
                )
            )
            method = 'getblock'
            payload = {'jsonrpc': '2.0', 'id': 5001, 'method': method, 'params': [block_hash, 3]}
            expected_result = {'height': height, 'hash': expected_hash, 'source': 0}
            identity = [expected_hash, 3]
            expected_counters[f'jsonrpc:good:{chain.value}:0:getblockhash'] = 1
        else:
            continue
        responses = await asyncio.gather(
            *(
                client.jsonrpc(resources.gateways[chain], resources.api_key, payload | {'id': 5100 + offset})
                for offset in range(10)
            )
        )
        for offset, response in enumerate(responses):
            _assert_jsonrpc_result(response, 5100 + offset, expected_result)
        retention_specs.append(
            PostgresRetentionAuditSpec(
                chain=chain,
                network=network,
                method=method,
                expected_cache_key=_cache_digest(method, identity),
                expected_sequence=height,
                expected_result=expected_result,
            )
        )
        expected_counters[f'jsonrpc:good:{chain.value}:0:{method}'] = 1
    counters = await _mock_counters(mock_url)
    if counters != expected_counters:
        raise RuntimeError(
            f'PostgreSQL retention cache upstream load counts mismatch: expected {expected_counters!r}, got {counters!r}.'
        )
    return (
        retention_specs,
        redis_ttl_specs,
        {
            'cache_keys': len(retention_specs),
            'requests_per_key': 10,
            'exact_loads_per_key': 1,
            'total_upstream_requests': sum(counters.values()),
            'counters': counters,
        },
    )


async def _publisher_soak(
    admin: GatewayClient,
    admin_peer: GatewayClient,
    resources: AccountResources,
    mock_url: str,
    inspector: RuntimeInspector,
) -> dict[str, object]:
    started_at = time.monotonic()
    rounds = 8
    responses_verified = 0
    previous_loads = {chain: 0 for chain, _network in CHAINS}
    load_history: dict[str, list[int]] = {chain.value: [] for chain, _network in CHAINS}
    for round_number in range(rounds):
        for chain_index, (chain, _network) in enumerate(CHAINS):
            request_id = 8000 + round_number * 100 + chain_index
            leader = admin if (chain_index + round_number) % 2 == 0 else admin_peer
            follower = admin_peer if leader is admin else admin
            leader_task = asyncio.create_task(
                leader.jsonrpc(resources.gateways[chain], resources.api_key, _redis_ttl_call(chain, request_id))
            )
            method = str(_redis_ttl_call(chain, 1)['method'])
            key = f'jsonrpc:good:{chain.value}:0:{method}'
            expected_load = previous_loads[chain] + 1
            await _wait_mock_counters(mock_url, {key: expected_load})
            follower_task = asyncio.create_task(
                follower.jsonrpc(resources.gateways[chain], resources.api_key, _redis_ttl_call(chain, request_id))
            )
            leader_response, follower_response = await asyncio.gather(leader_task, follower_task)
            expected = _redis_ttl_result(chain)
            _assert_jsonrpc_result(leader_response, request_id, expected)
            _assert_jsonrpc_result(follower_response, request_id, expected)
            responses_verified += 2
            await inspector.audit_cache_flight_count(0)
            count = (await _mock_counters(mock_url)).get(key, 0)
            if count != expected_load:
                raise RuntimeError(
                    f'Publisher soak single-flight failed for {chain.value} in round {round_number}: '
                    f'previous={previous_loads[chain]}, found={count}.'
                )
            previous_loads[chain] = count
            load_history[chain.value].append(count)
        await asyncio.sleep(1.1)

    counters = await _mock_counters(mock_url)
    peer_counts, _replica_ips = await _audit_mock_peers(mock_url)
    loads: dict[str, int] = {}
    for chain, _network in CHAINS:
        method = str(_redis_ttl_call(chain, 1)['method'])
        key = f'jsonrpc:good:{chain.value}:0:{method}'
        count = counters.get(key, 0)
        if count != rounds:
            raise RuntimeError(f'Publisher soak load count must equal {rounds} for {chain.value}, found {count}.')
        loads[chain.value] = count
    return {
        'rounds': rounds,
        'requests': responses_verified,
        'elapsed_ms': round((time.monotonic() - started_at) * 1000),
        'upstream_loads': loads,
        'upstream_load_history': load_history,
        'api_replica_peers': peer_counts,
        'semantic_responses_verified': responses_verified,
    }


async def _negative_calls(
    client: GatewayClient,
    resources: AccountResources,
    extras: dict[str, EndpointResource],
    method_routes: list[tuple[str, RouteResource]],
    mock_url: str,
    good_endpoint_id: str,
    inspector: RuntimeInspector,
) -> dict[str, object]:
    gateway = resources.gateways[Chain.ETHEREUM]
    malformed = await client.jsonrpc(gateway, resources.api_key, {}, raw=b'{')
    invalid = await client.jsonrpc(gateway, resources.api_key, [])
    missing = await client.jsonrpc(gateway, None, _redis_ttl_call(Chain.ETHEREUM, 6000))
    wrong = await client.jsonrpc(gateway, resources.api_key + 'x', _redis_ttl_call(Chain.ETHEREUM, 6001))
    application = await client.jsonrpc(
        gateway, resources.api_key, {'jsonrpc': '2.0', 'id': 6002, 'method': 'integration_error', 'params': []}
    )
    codes = [
        malformed.json()['error']['code'],
        invalid.json()['error']['code'],
        missing.json()['error']['code'],
        wrong.json()['error']['code'],
    ]
    if codes != [-32700, -32600, -32001, -32001] or application.json()['error']['code'] != -32602:
        raise RuntimeError(f'Negative public request contract failed: {codes!r}.')

    gateway_id = gateway['id']
    for behavior, method in (('invalid', 'integration_invalid_upstream'), ('timeout', 'integration_timeout_upstream')):
        route = await client.create_method_route(gateway_id, [method], extras[behavior].id)
        method_routes.append((gateway_id, route))
        response = await client.jsonrpc(
            gateway, resources.api_key, {'jsonrpc': '2.0', 'id': 6100, 'method': method, 'params': []}
        )
        if response.json()['error']['code'] != -32005:
            raise RuntimeError(f'{behavior} upstream contract failed.')

    height = HEIGHTS[Chain.ETHEREUM] - 77
    wrong_call = {'jsonrpc': '2.0', 'id': 6200, 'method': 'eth_getBlockByNumber', 'params': [hex(height), False]}
    saved_route = resources.routes[Chain.ETHEREUM]
    wrong_route = await client.replace_jsonrpc_route(gateway_id, saved_route, [extras['wrong_height'].id], max_attempts=1)
    resources.routes[Chain.ETHEREUM] = wrong_route
    try:
        await _clear_mock_counters(mock_url)
        wrong_response = await client.jsonrpc(gateway, resources.api_key, wrong_call)
        wrong_payload = _assert_success(wrong_response)
        if wrong_payload['result'].get('number') != hex(height + 1):
            raise RuntimeError('Wrong-height mutation Endpoint did not return the injected mismatch.')
        await inspector.audit_postgres_retention_absent(
            PostgresRetentionAuditSpec(
                chain=Chain.ETHEREUM,
                network=Network.MAINNET,
                method='eth_getBlockByNumber',
                expected_cache_key=_cache_digest('eth_getBlockByNumber', [hex(height), False]),
                expected_sequence=height,
                expected_result=wrong_payload['result'],
            )
        )
    finally:
        restored_route = await client.replace_jsonrpc_route(gateway_id, wrong_route, [good_endpoint_id], max_attempts=1)
        resources.routes[Chain.ETHEREUM] = restored_route
    corrected_response = await client.jsonrpc(gateway, resources.api_key, wrong_call | {'id': 6201})
    corrected_result = {'number': hex(height), 'hash': f'0x{height:064x}', 'source': 0}
    _assert_jsonrpc_result(corrected_response, 6201, corrected_result)
    wrong_height_counters = await _mock_counters(mock_url)
    expected_wrong_height_counters = {
        'jsonrpc:wrong_height:ethereum:0:eth_getBlockByNumber': 1,
        'jsonrpc:good:ethereum:0:eth_getBlockByNumber': 1,
    }
    if wrong_height_counters != expected_wrong_height_counters:
        raise RuntimeError(
            f'Wrong-height cache rejection loads mismatch: expected {expected_wrong_height_counters!r}, '
            f'got {wrong_height_counters!r}.'
        )
    tron_gateway = resources.gateways[Chain.TRON]
    not_found = await client.http_api(tron_gateway, resources.api_key, 'GET', 'unknown/path')
    not_allowed = await client.http_api(tron_gateway, resources.api_key, 'DELETE', 'wallet/getnowblock')
    if (not_found.status_code, not_allowed.status_code) != (404, 405):
        raise RuntimeError('TRON negative request contract failed.')
    return {
        'jsonrpc_codes': codes + [-32602, -32005, -32005],
        'tron_statuses': [404, 405],
        'wrong_height_not_cached': True,
        'wrong_height_loads': wrong_height_counters,
    }


async def _admission_calls(client: GatewayClient, resources: AccountResources) -> dict[str, int]:
    saved = await client.get_jsonrpc_policy()
    changed = await client.update_jsonrpc_policy(
        {
            'expected_version': saved['version'],
            'mode': 'enforce',
            'global_limit': {'rps': 1000, 'burst': 1000},
            'ip_limit': {'rps': 1000, 'burst': 1000},
            'account_limit': {'rps': 1, 'burst': 20},
            'app_limit': {'rps': 1, 'burst': 20},
        }
    )
    await asyncio.sleep(1.5)
    try:
        started_at = time.monotonic()
        responses = await asyncio.gather(
            *(
                client.jsonrpc(
                    resources.gateways[Chain.ETHEREUM],
                    resources.api_key,
                    {'jsonrpc': '2.0', 'id': 7000 + offset, 'method': f'integration_admission_{offset}', 'params': []},
                )
                for offset in range(50)
            )
        )
        elapsed_seconds = time.monotonic() - started_at
        limited = sum(response.json().get('error', {}).get('code') == -32029 for response in responses)
        succeeded = sum('result' in response.json() for response in responses)
        max_succeeded = 20 + math.ceil(elapsed_seconds) + 2
        if limited == 0 or succeeded > max_succeeded or limited + succeeded != 50:
            raise RuntimeError(f'Admission invariant failed: success={succeeded}, limited={limited}.')
        return {
            'requests': 50,
            'success': succeeded,
            'limited': limited,
            'elapsed_ms': round(elapsed_seconds * 1000),
            'max_success': max_succeeded,
        }
    finally:
        await client.update_jsonrpc_policy(
            {
                'expected_version': changed['version'],
                'mode': saved['mode'],
                'global_limit': saved['global_limit'],
                'ip_limit': saved['ip_limit'],
                'account_limit': saved['account_limit'],
                'app_limit': saved['app_limit'],
            }
        )
        await asyncio.sleep(1.5)


async def _cleanup_account(
    client: GatewayClient,
    resources: AccountResources,
    method_routes: list[tuple[str, RouteResource]],
    errors: list[str],
) -> None:
    for gateway_id, route in reversed(method_routes):
        try:
            await client.delete_method_route(gateway_id, route)
        except Exception as exc:
            errors.append(f'Method Route {route.id} cleanup failed: {exc!r}')
    for chain, route in list(resources.routes.items()):
        try:
            resources.routes[chain] = await client.replace_jsonrpc_route(resources.gateways[chain]['id'], route, [])
        except Exception as exc:
            errors.append(f'{chain.value} Route cleanup failed: {exc!r}')
    if resources.http_route is not None:
        try:
            resources.http_route = await client.replace_http_route(
                resources.gateways[Chain.TRON]['id'], resources.http_route, []
            )
        except Exception as exc:
            errors.append(f'HTTP Route cleanup failed: {exc!r}')
    for endpoint in reversed(resources.endpoints):
        try:
            await client.delete_endpoint(endpoint.id)
        except Exception as exc:
            errors.append(f'Endpoint {endpoint.id} cleanup failed: {exc!r}')
    try:
        await client.delete_app(resources.app_id)
    except Exception as exc:
        errors.append(f'App {resources.app_id} cleanup failed: {exc!r}')
