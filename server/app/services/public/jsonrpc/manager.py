import json
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from time import perf_counter
from typing import Protocol
from uuid import uuid4

import orjson
from fastlog import log

from app.model.account import AccountRole
from app.model.blockchain import Chain, Network
from app.model.jsonrpc_forwarding import (
    JsonRpcForwardingFailure,
    JsonRpcForwardingFailureCode,
    JsonRpcForwardingResult,
    JsonRpcRoutePlan,
)
from app.model.public import (
    JsonRpcCall,
    JsonRpcCallResult,
    JsonRpcError,
    JsonRpcErrorResponse,
    JsonRpcProtocolError,
    JsonRpcSuccessResponse,
    PublicAccessFailure,
    PublicAccessFailureCode,
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
    parse_jsonrpc_call,
)
from app.model.system_jsonrpc_cache import SystemJsonRpcCacheResult
from app.model.transport import Transport
from app.model.usage import GatewayUsageEvent
from app.services.admission import AdmissionDecision
from app.services.usage.interface import GatewayUsage


class PublicGatewayAccess(Protocol):
    def match_host(self, host: str | None, transport: Transport) -> PublicGatewayAddress | None: ...

    async def authenticate(
        self,
        path_key: str | None,
        authorization: str | None,
    ) -> PublicGatewayIdentity | PublicAccessFailure: ...

    async def get_context(
        self,
        address: PublicGatewayAddress,
        identity: PublicGatewayIdentity,
    ) -> PublicGatewayContext | PublicAccessFailure: ...


class JsonRpcAdmission(Protocol):
    def acquire_inflight(self) -> AbstractAsyncContextManager[AdmissionDecision]: ...

    async def acquire_pre_auth(self, client_ip: str) -> AdmissionDecision: ...

    async def acquire_post_auth(self, account_id: str, app_id: str) -> AdmissionDecision: ...


class JsonRpcForwarding(Protocol):
    async def load_plan(
        self,
        *,
        account_id: str,
        gateway_id: str,
        chain: Chain,
        network: Network,
        method: str,
    ) -> JsonRpcRoutePlan | JsonRpcForwardingFailure: ...

    async def forward(self, plan: JsonRpcRoutePlan, call: JsonRpcCall) -> JsonRpcForwardingResult: ...


class SystemResultCache(Protocol):
    async def get_result_with_usage(
        self,
        *,
        chain: Chain,
        network: Network,
        call: JsonRpcCall,
        loader: 'JsonRpcLoader',
    ) -> SystemJsonRpcCacheResult: ...

    async def lookup_result_with_usage(
        self, *, chain: Chain, network: Network, call: JsonRpcCall
    ) -> SystemJsonRpcCacheResult: ...


class JsonRpcLoader(Protocol):
    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingResult | None: ...


RPC_AUTHENTICATION_FAILED = -32001
RPC_GATEWAY_NOT_FOUND = -32002
RPC_GATEWAY_DISABLED = -32003
RPC_NO_ENDPOINT = -32004
RPC_ENDPOINT_FAILED = -32005
RPC_ENDPOINT_INVALID = -32006
RPC_RATE_LIMITED = -32029
RPC_INTERNAL_ERROR = -32603
RPC_CACHE_HIT_HEADER = 'X-RPC-Gateway-Cache'

_ERROR_MESSAGES: dict[int, str] = {
    RPC_AUTHENTICATION_FAILED: 'Authentication failed.',
    RPC_GATEWAY_NOT_FOUND: 'Gateway not found.',
    RPC_GATEWAY_DISABLED: 'Gateway is disabled.',
    RPC_NO_ENDPOINT: 'No available Endpoint.',
    RPC_ENDPOINT_FAILED: 'Endpoint request failed.',
    RPC_ENDPOINT_INVALID: 'Endpoint returned an invalid JSON-RPC response.',
    RPC_RATE_LIMITED: 'Rate limit exceeded.',
    RPC_INTERNAL_ERROR: 'Internal error.',
}

_ACCESS_ERROR_CODES: dict[PublicAccessFailureCode, int] = {
    PublicAccessFailureCode.AUTHENTICATION_FAILED: RPC_AUTHENTICATION_FAILED,
    PublicAccessFailureCode.GATEWAY_NOT_FOUND: RPC_GATEWAY_NOT_FOUND,
    PublicAccessFailureCode.GATEWAY_DISABLED: RPC_GATEWAY_DISABLED,
    PublicAccessFailureCode.INTERNAL: RPC_INTERNAL_ERROR,
}


def _error_response(
    code: int,
    message: str,
    request_id: str | int | None,
    *,
    data: dict[str, object] | None = None,
) -> JsonRpcErrorResponse:
    error_data = data if data is not None else {'type': 'gateway_error'}
    error = JsonRpcError(code=code, message=message, data=error_data)
    return JsonRpcErrorResponse(jsonrpc='2.0', id=request_id, error=error)


def _gateway_error(code: int, request_id: str | int | None) -> JsonRpcErrorResponse:
    return _error_response(code, _ERROR_MESSAGES[code], request_id)


def _rate_limit_error(request_id: str | int | None, retry_after_ms: int) -> JsonRpcErrorResponse:
    data: dict[str, object] = {
        'type': 'gateway_error',
        'reason': 'rate_limited',
        'retry_after_ms': retry_after_ms,
    }
    return _error_response(RPC_RATE_LIMITED, _ERROR_MESSAGES[RPC_RATE_LIMITED], request_id, data=data)


def _retry_headers(retry_after_ms: int) -> dict[str, str]:
    retry_after_seconds = max(1, ceil(retry_after_ms / 1000))
    return {'Retry-After': str(retry_after_seconds)}


def _cache_headers(cache_hit: bool) -> dict[str, str]:
    return {RPC_CACHE_HIT_HEADER: 'HIT'} if cache_hit else {}


@dataclass(frozen=True, slots=True, kw_only=True)
class _GatewayCallResult:
    response: JsonRpcErrorResponse | bytes | None
    successful: bool
    cache_eligible: bool = False
    cache_hit: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class _PlanBoundLoader:
    forwarding: JsonRpcForwarding
    plan: JsonRpcRoutePlan

    async def load(self, *, chain: Chain, network: Network, call: JsonRpcCall) -> JsonRpcForwardingResult:
        return await self.forwarding.forward(self.plan, call)


class PublicJsonRpcManager:
    def __init__(
        self,
        access: PublicGatewayAccess,
        admission: JsonRpcAdmission,
        forwarding: JsonRpcForwarding,
        system_cache: SystemResultCache | None = None,
        *,
        admin_forwarding: JsonRpcForwarding | None = None,
        usage: GatewayUsage | None = None,
    ) -> None:
        self._access = access
        self._admission = admission
        self._forwarding = forwarding
        self._admin_forwarding = admin_forwarding if admin_forwarding is not None else forwarding
        self._system_cache = system_cache
        self._usage = usage

    async def call(
        self,
        *,
        host: str | None,
        body: bytes,
        path_key: str | None,
        authorization: str | None,
        client_ip: str,
    ) -> JsonRpcCallResult:
        """Map public access and JSON-RPC orchestration failures to the stable protocol contract."""
        address = self._access.match_host(host, Transport.JSONRPC)
        if address is None:
            return JsonRpcCallResult(response=None, status_code=404)
        try:
            async with self._admission.acquire_inflight() as inflight:
                if inflight.enforced:
                    return self._limited_body_result(body, inflight)
                try:
                    pre_auth = await self._admission.acquire_pre_auth(client_ip)
                except Exception:
                    failure = PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
                    return self._failed_body_result(body, failure)
                if pre_auth.enforced:
                    return self._limited_body_result(body, pre_auth)
                try:
                    call = parse_jsonrpc_call(body)
                except JsonRpcProtocolError as exc:
                    response = _error_response(exc.code, exc.message, exc.request_id)
                    return JsonRpcCallResult(response=response, status_code=200)
                return await self._call_jsonrpc(
                    call,
                    address=address,
                    path_key=path_key,
                    authorization=authorization,
                    request_bytes=len(body),
                )
        except Exception as exc:
            log.error(f'Public JSON-RPC call failed unexpectedly | Error:{exc!r}')
            failure = PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
            return self._failed_body_result(body, failure)

    async def _call_jsonrpc(
        self,
        call: JsonRpcCall,
        *,
        address: PublicGatewayAddress,
        path_key: str | None,
        authorization: str | None,
        request_bytes: int,
    ) -> JsonRpcCallResult:
        try:
            identity = await self._access.authenticate(path_key, authorization)
            if isinstance(identity, PublicAccessFailure):
                return self._failed_call_result(call, identity)
            admission = await self._admission.acquire_post_auth(identity.account_id, identity.app_id)
            if admission.enforced:
                return self._limited_call_result(call, admission)
            context = await self._access.get_context(address, identity)
            if isinstance(context, PublicAccessFailure):
                return self._failed_call_result(call, context)
        except Exception as exc:
            log.error(f'Public JSON-RPC call failed unexpectedly | Error:{exc!r}')
            failure = PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
            return self._failed_call_result(call, failure)

        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            result = await self._forward(context, call)
        except Exception as exc:
            log.error(f'Public JSON-RPC forwarding failed unexpectedly | Gateway:{context.gateway_id} | Error:{exc!r}')
            response = _gateway_error(RPC_INTERNAL_ERROR, call.request_id())
            result = _GatewayCallResult(response=response, successful=False)

        if call.is_notification:
            call_result = JsonRpcCallResult(response=None, status_code=204)
        elif isinstance(result.response, bytes):
            call_result = JsonRpcCallResult(
                response=None,
                status_code=200,
                headers=_cache_headers(result.cache_hit),
                raw_result=result.response,
                request_id=call.request_id(),
            )
        else:
            response = result.response or _gateway_error(RPC_INTERNAL_ERROR, call.request_id())
            call_result = JsonRpcCallResult(
                response=response,
                status_code=200,
                headers=_cache_headers(result.cache_hit),
            )
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        await self._record_usage(
            context,
            call,
            call_result,
            result,
            started_at=started_at,
            duration_ms=duration_ms,
            request_bytes=request_bytes,
        )
        return call_result

    async def _forward(self, context: PublicGatewayContext, call: JsonRpcCall) -> _GatewayCallResult:
        forwarding = self._admin_forwarding if context.account_role is AccountRole.ADMIN else self._forwarding
        plan = await forwarding.load_plan(
            account_id=context.account_id,
            gateway_id=context.gateway_id,
            chain=context.chain,
            network=context.network,
            method=call.method,
        )
        cache_result: SystemJsonRpcCacheResult | None = None
        if self._system_cache is not None:
            if context.account_role is AccountRole.ADMIN and isinstance(plan, JsonRpcRoutePlan) and plan.targets:
                loader = _PlanBoundLoader(forwarding=forwarding, plan=plan)
                cache_result = await self._system_cache.get_result_with_usage(
                    chain=context.chain,
                    network=context.network,
                    call=call,
                    loader=loader,
                )
            else:
                cache_result = await self._system_cache.lookup_result_with_usage(
                    chain=context.chain,
                    network=context.network,
                    call=call,
                )
            cached = cache_result.value
            if isinstance(cached, bytes):
                return _GatewayCallResult(
                    response=cached,
                    successful=True,
                    cache_eligible=cache_result.eligible,
                    cache_hit=cache_result.hit,
                )
            if cached is not None:
                return self._with_cache(self._forwarded_result(cached, call), cache_result)
        if isinstance(plan, JsonRpcRoutePlan) and not plan.targets:
            failure = JsonRpcForwardingFailure(code=JsonRpcForwardingFailureCode.NO_ENDPOINT)
            return self._with_cache(self._forwarding_failure(failure, call), cache_result)
        if isinstance(plan, JsonRpcForwardingFailure):
            return self._with_cache(self._forwarding_failure(plan, call), cache_result)
        result = await forwarding.forward(plan, call)
        return self._with_cache(self._forwarded_result(result, call), cache_result)

    @classmethod
    def _forwarded_result(cls, result: JsonRpcForwardingResult, call: JsonRpcCall) -> _GatewayCallResult:
        if isinstance(result, JsonRpcForwardingFailure):
            return cls._forwarding_failure(result, call)
        response = result.response
        if isinstance(response, JsonRpcSuccessResponse):
            return _GatewayCallResult(response=response.result, successful=True)
        if response is not None and response.id != call.request_id():
            response = response.model_copy(update={'id': call.request_id()})
        return _GatewayCallResult(response=response, successful=response is None)

    @staticmethod
    def _forwarding_failure(result: JsonRpcForwardingFailure, call: JsonRpcCall) -> _GatewayCallResult:
        code = {
            JsonRpcForwardingFailureCode.NO_ENDPOINT: RPC_NO_ENDPOINT,
            JsonRpcForwardingFailureCode.ATTEMPTS_FAILED: RPC_ENDPOINT_FAILED,
            JsonRpcForwardingFailureCode.INTERNAL: RPC_INTERNAL_ERROR,
        }[result.code]
        return _GatewayCallResult(response=_gateway_error(code, call.request_id()), successful=False)

    @staticmethod
    def _with_cache(result: _GatewayCallResult, cache: SystemJsonRpcCacheResult | None) -> _GatewayCallResult:
        if cache is None:
            return result
        return _GatewayCallResult(
            response=result.response,
            successful=result.successful,
            cache_eligible=cache.eligible,
            cache_hit=cache.hit,
        )

    async def _record_usage(
        self,
        context: PublicGatewayContext,
        call: JsonRpcCall,
        call_result: JsonRpcCallResult,
        gateway_result: _GatewayCallResult,
        *,
        started_at: datetime,
        duration_ms: int,
        request_bytes: int,
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
                method=call.method,
                started_at=started_at,
                successful=gateway_result.successful,
                duration_ms=duration_ms,
                request_bytes=request_bytes,
                response_bytes=self._response_bytes(call_result),
                cache_eligible=gateway_result.cache_eligible,
                cache_hit=gateway_result.cache_hit,
            )
            self._usage.submit(event)
        except Exception as exc:
            log.warning(f'Gateway Usage recorder failed | Gateway:{context.gateway_id} | Error:{exc!r}')

    @staticmethod
    def _response_bytes(result: JsonRpcCallResult) -> int:
        if result.raw_result is not None:
            prefix = b'{"jsonrpc":"2.0","id":' + PublicJsonRpcManager._dump_json(result.request_id) + b',"result":'
            return len(prefix) + len(result.raw_result) + 1
        if result.response is None:
            return 0
        content = result.response.model_dump(mode='json', exclude_unset=True)
        return len(PublicJsonRpcManager._dump_json(content))

    @staticmethod
    def _dump_json(content: object) -> bytes:
        try:
            return orjson.dumps(content)
        except TypeError:
            return json.dumps(
                content,
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                separators=(',', ':'),
            ).encode()

    @staticmethod
    def _failed_call_result(call: JsonRpcCall, failure: PublicAccessFailure) -> JsonRpcCallResult:
        if call.is_notification:
            return JsonRpcCallResult(response=None, status_code=204)
        response = _gateway_error(_ACCESS_ERROR_CODES[failure.code], call.request_id())
        return JsonRpcCallResult(response=response, status_code=200)

    @staticmethod
    def _limited_call_result(call: JsonRpcCall, decision: AdmissionDecision) -> JsonRpcCallResult:
        headers = _retry_headers(decision.retry_after_ms)
        if call.is_notification:
            return JsonRpcCallResult(response=None, status_code=204, headers=headers)
        response = _rate_limit_error(call.request_id(), decision.retry_after_ms)
        return JsonRpcCallResult(response=response, status_code=200, headers=headers)

    @classmethod
    def _failed_body_result(cls, body: bytes, failure: PublicAccessFailure) -> JsonRpcCallResult:
        try:
            call = parse_jsonrpc_call(body)
        except JsonRpcProtocolError:
            response = _gateway_error(_ACCESS_ERROR_CODES[failure.code], None)
            return JsonRpcCallResult(response=response, status_code=200)
        return cls._failed_call_result(call, failure)

    @classmethod
    def _limited_body_result(cls, body: bytes, decision: AdmissionDecision) -> JsonRpcCallResult:
        try:
            call = parse_jsonrpc_call(body)
        except JsonRpcProtocolError:
            headers = _retry_headers(decision.retry_after_ms)
            response = _rate_limit_error(None, decision.retry_after_ms)
            return JsonRpcCallResult(response=response, status_code=200, headers=headers)
        return cls._limited_call_result(call, decision)
