from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from fastlog import log

from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointHttpApiRequest
from app.model.http_api_forwarding import (
    HttpApiForwardingFailure,
    HttpApiForwardingFailureCode,
    HttpApiForwardingResult,
    HttpApiRoutePlan,
)
from app.model.public import (
    PublicAccessFailure,
    PublicAccessFailureCode,
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
    PublicHttpApiRequest,
    PublicHttpApiResult,
    TronHttpApiFamily,
)
from app.model.transport import Transport
from app.model.usage import GatewayUsageEvent
from app.services.admission import AdmissionDecision
from app.services.public.http_api.tron import TronHttpApiAdapter
from app.services.usage.interface import GatewayUsage
from app.services.usage.operation import normalize_http_operation

_RESPONSE_HEADERS = frozenset({'content-type', 'cache-control', 'etag', 'last-modified', 'expires', 'retry-after'})


class HttpApiAdmission(Protocol):
    def acquire_inflight(self) -> AbstractAsyncContextManager[AdmissionDecision]: ...

    async def acquire_pre_auth(self, client_ip: str) -> AdmissionDecision: ...

    async def acquire_post_auth(self, account_id: str, app_id: str) -> AdmissionDecision: ...


class PublicGatewayAccess(Protocol):
    def match_host(self, host: str | None, transport: Transport) -> PublicGatewayAddress | None: ...

    async def authenticate(
        self, path_key: str | None, authorization: str | None
    ) -> PublicGatewayIdentity | PublicAccessFailure: ...

    async def get_context(
        self, address: PublicGatewayAddress, identity: PublicGatewayIdentity
    ) -> PublicGatewayContext | PublicAccessFailure: ...


class HttpApiForwarding(Protocol):
    async def load_plan(
        self, *, account_id: str, gateway_id: str, chain: Chain, network: Network
    ) -> HttpApiRoutePlan | HttpApiForwardingFailure: ...

    async def forward(self, plan: HttpApiRoutePlan, request: EndpointHttpApiRequest) -> HttpApiForwardingResult: ...


class PublicHttpApiManager:
    def __init__(
        self,
        access: PublicGatewayAccess,
        admission: HttpApiAdmission,
        forwarding: HttpApiForwarding,
        usage: GatewayUsage | None = None,
    ) -> None:
        self._access = access
        self._admission = admission
        self._forwarding = forwarding
        self._usage = usage

    async def call(
        self,
        *,
        host: str | None,
        method: str,
        raw_path: str,
        headers: list[tuple[str, str]],
        query: list[tuple[str, str]],
        body: bytes,
        authorization: str | None,
        client_ip: str,
    ) -> PublicHttpApiResult:
        address = self._access.match_host(host, Transport.HTTP_API)
        if address is None:
            return PublicHttpApiResult(status_code=404, body=b'', protocol_matched=False)
        try:
            async with self._admission.acquire_inflight() as inflight:
                if inflight.enforced:
                    return TronHttpApiAdapter.error(self._family(raw_path), 429, 'Rate limit exceeded.')
                pre_auth = await self._admission.acquire_pre_auth(client_ip)
                if pre_auth.enforced:
                    return TronHttpApiAdapter.error(self._family(raw_path), 429, 'Rate limit exceeded.')
                parsed = TronHttpApiAdapter.parse(method, raw_path, headers=headers, query=query, body=body)
                if isinstance(parsed, PublicHttpApiResult):
                    return parsed
                return await self._authenticated_call(address, parsed, authorization)
        except Exception as exc:
            log.error(f'Public HTTP API call failed unexpectedly | Error:{exc!r}')
            return TronHttpApiAdapter.error(self._family(raw_path), 500, 'Internal error.')

    async def _authenticated_call(
        self,
        address: PublicGatewayAddress,
        request: PublicHttpApiRequest,
        authorization: str | None,
    ) -> PublicHttpApiResult:
        identity = await self._access.authenticate(request.path_key, authorization)
        if isinstance(identity, PublicAccessFailure):
            return self._access_error(request, identity)
        post_auth = await self._admission.acquire_post_auth(identity.account_id, identity.app_id)
        if post_auth.enforced:
            return TronHttpApiAdapter.error(request.family, 429, 'Rate limit exceeded.')
        context = await self._access.get_context(address, identity)
        if isinstance(context, PublicAccessFailure):
            return self._access_error(request, context)
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = await self._forward_request(context, request)
        except Exception as exc:
            log.error(f'Public HTTP API forwarding failed unexpectedly | Gateway:{context.gateway_id} | Error:{exc!r}')
            result = TronHttpApiAdapter.error(request.family, 500, 'Internal error.')
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        await self._record_usage(context, request, result, started_at=started_at, duration_ms=duration_ms)
        return result

    async def _forward_request(
        self,
        context: PublicGatewayContext,
        request: PublicHttpApiRequest,
    ) -> PublicHttpApiResult:
        plan = await self._forwarding.load_plan(
            account_id=context.account_id,
            gateway_id=context.gateway_id,
            chain=context.chain,
            network=context.network,
        )
        if isinstance(plan, HttpApiForwardingFailure):
            return self._forwarding_error(request, plan)
        result = await self._forwarding.forward(
            plan,
            EndpointHttpApiRequest(
                method=request.method,
                path=request.path,
                headers=request.headers,
                query=request.query,
                content=request.body,
            ),
        )
        if isinstance(result, HttpApiForwardingFailure):
            return self._forwarding_error(request, result)
        response = result.response
        headers = tuple((name, value) for name, value in response.headers if name.casefold() in _RESPONSE_HEADERS)
        return PublicHttpApiResult(status_code=response.status_code, body=response.body, headers=headers)

    async def _record_usage(
        self,
        context: PublicGatewayContext,
        request: PublicHttpApiRequest,
        result: PublicHttpApiResult,
        *,
        started_at: datetime,
        duration_ms: int,
    ) -> None:
        if self._usage is None:
            return
        try:
            event = GatewayUsageEvent(
                event_id=uuid4().hex,
                account_id=context.account_id,
                app_id=context.app_id,
                gateway_id=context.gateway_id,
                chain=context.chain,
                network=context.network,
                method=normalize_http_operation(request.method, request.path),
                started_at=started_at,
                successful=200 <= result.status_code < 300,
                duration_ms=duration_ms,
                request_bytes=len(request.body),
                response_bytes=len(result.body),
            )
            self._usage.submit(event)
        except Exception as exc:
            log.warning(f'Gateway Usage recorder failed | Gateway:{context.gateway_id} | Error:{exc!r}')

    @staticmethod
    def _access_error(request: PublicHttpApiRequest, failure: PublicAccessFailure) -> PublicHttpApiResult:
        status_code, message = {
            PublicAccessFailureCode.AUTHENTICATION_FAILED: (401, 'Authentication failed.'),
            PublicAccessFailureCode.GATEWAY_NOT_FOUND: (404, 'Gateway not found.'),
            PublicAccessFailureCode.GATEWAY_DISABLED: (503, 'Gateway is disabled.'),
            PublicAccessFailureCode.INTERNAL: (500, 'Internal error.'),
        }[failure.code]
        return TronHttpApiAdapter.error(request.family, status_code, message)

    @staticmethod
    def _forwarding_error(
        request: PublicHttpApiRequest,
        failure: HttpApiForwardingFailure,
    ) -> PublicHttpApiResult:
        if failure.response is not None:
            response = failure.response
            headers = tuple((name, value) for name, value in response.headers if name.casefold() in _RESPONSE_HEADERS)
            return PublicHttpApiResult(status_code=response.status_code, body=response.body, headers=headers)
        status_code, message = {
            HttpApiForwardingFailureCode.NO_ENDPOINT: (503, 'No available Endpoint.'),
            HttpApiForwardingFailureCode.ATTEMPTS_FAILED: (502, 'Endpoint request failed.'),
            HttpApiForwardingFailureCode.INTERNAL: (500, 'Internal error.'),
        }[failure.code]
        return TronHttpApiAdapter.error(request.family, status_code, message)

    @staticmethod
    def _family(path: str) -> TronHttpApiFamily:
        segments = path.strip('/').split('/')
        if 'v1' in (segment.casefold() for segment in segments[:2]):
            return TronHttpApiFamily.V1
        return TronHttpApiFamily.WALLET
