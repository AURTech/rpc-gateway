import asyncio

import orjson

from app.clients.provider.base import AccountActiveCheck, ProviderDiscoveryFailure
from app.clients.provider.networks import EVM_NETWORK_BY_CHAIN_ID
from app.clients.transport import HttpAuth, HttpTransport
from app.infra.outbound_policy import build_outbound_target_policy
from app.model.blockchain import Chain, Network


async def probe_evm_endpoints(
    transport: HttpTransport,
    targets: list[tuple[str, str, HttpAuth]],
    check_account_active: AccountActiveCheck,
    *,
    concurrency: int = 10,
) -> tuple[dict[str, tuple[Chain, Network]], list[ProviderDiscoveryFailure]]:
    semaphore = asyncio.Semaphore(concurrency)
    policy = build_outbound_target_policy()

    async def probe(external_id: str, url: str, auth: HttpAuth) -> tuple[str, tuple[Chain, Network] | None, str | None]:
        async with semaphore:
            await check_account_active()
            body = orjson.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_chainId', 'params': []})
            try:
                await policy.validate_url(url, allowed_schemes=frozenset({'http', 'https'}))
                response = await transport.request(
                    'POST',
                    url,
                    headers={'Content-Type': 'application/json'},
                    content=body,
                    auth=auth,
                    max_response_bytes=1024 * 1024,
                )
                if not 200 <= response.status_code <= 299:
                    return external_id, None, 'Endpoint probe returned a non-success status.'
                payload = orjson.loads(response.body)
                chain_id_value = payload.get('result') if isinstance(payload, dict) else None
                if not isinstance(chain_id_value, str):
                    return external_id, None, 'Endpoint probe returned an invalid chain id.'
                chain_id = int(chain_id_value.removeprefix('0x'), 16)
            except Exception:
                return external_id, None, 'Endpoint probe failed.'
            pair = EVM_NETWORK_BY_CHAIN_ID.get(chain_id)
            if pair is None:
                return external_id, None, 'Endpoint chain is unsupported.'
            return external_id, pair, None

    results = await asyncio.gather(*(probe(external_id, url, auth) for external_id, url, auth in targets))
    pairs: dict[str, tuple[Chain, Network]] = {}
    failures: list[ProviderDiscoveryFailure] = []
    for external_id, pair, error in results:
        if pair is not None:
            pairs[external_id] = pair
        elif error is not None:
            failures.append(ProviderDiscoveryFailure(external_id=external_id, error=error))
    return pairs, failures
