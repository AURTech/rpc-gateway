from app.clients.endpoint import EndpointHttpClient
from app.clients.transport import (
    HttpTransportConfigError,
    HttpTransportError,
    HttpTransportResponse,
    HttpTransportResponseError,
    HttpTransportResponseTooLargeError,
    HttpTransportTimeoutError,
)
from app.infra.outbound_policy import HTTP_OUTBOUND_SCHEMES, OutboundTargetError, OutboundTargetPolicy
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointProtocol, EndpointTrustLevel
from app.model.endpoint.access import (
    EndpointAccessFailure,
    EndpointAccessFailureCode,
    EndpointAccessResult,
    EndpointAccessSuccess,
    EndpointDescriptor,
    EndpointHttpApiRequest,
    EndpointJsonRpcRequest,
    EndpointRequest,
    EndpointResponse,
)
from app.orm.endpoint import Endpoint
from app.services.endpoint.crypto import EndpointSecretConfigError, decrypt_endpoint_url
from app.services.endpoint.transport import build_endpoint_connection


def _to_descriptor(endpoint: Endpoint) -> EndpointDescriptor:
    return EndpointDescriptor(
        id=endpoint.id,
        account_id=endpoint.account_id,
        chain=Chain(endpoint.chain),
        network=Network(endpoint.network),
        protocol=EndpointProtocol(endpoint.protocol),
        enabled=endpoint.enabled,
        trust_level=EndpointTrustLevel(endpoint.trust_level),
        version=endpoint.version,
    )


def _to_response(response: HttpTransportResponse) -> EndpointResponse:
    return EndpointResponse(
        status_code=response.status_code,
        headers=tuple(response.headers.multi_items()),
        body=response.body,
        request_bytes=response.request_bytes,
        response_bytes=response.response_bytes,
    )


class EndpointAccessManager:
    def __init__(self, client: EndpointHttpClient, target_policy: OutboundTargetPolicy) -> None:
        self._client = client
        self._target_policy = target_policy

    async def get_descriptor(self, account_id: str, endpoint_id: str) -> EndpointDescriptor | None:
        endpoint = await Endpoint.filter(id=endpoint_id, account_id=account_id, deleted_at=None).first()
        return _to_descriptor(endpoint) if endpoint is not None else None

    async def list_descriptors(
        self,
        account_id: str,
        *,
        chain: Chain | None = None,
        network: Network | None = None,
        protocol: EndpointProtocol | None = None,
        enabled: bool | None = None,
    ) -> list[EndpointDescriptor]:
        query = Endpoint.filter(account_id=account_id, deleted_at=None)
        if chain is not None:
            query = query.filter(chain=chain)
        if network is not None:
            query = query.filter(network=network)
        if protocol is not None:
            query = query.filter(protocol=protocol)
        if enabled is not None:
            query = query.filter(enabled=enabled)
        endpoints = await query.order_by('created_at', 'id')
        return [_to_descriptor(endpoint) for endpoint in endpoints]

    async def execute(self, account_id: str, endpoint_id: str, request: EndpointRequest) -> EndpointAccessResult:
        """Execute one request without exposing connection configuration.

        The result contains stable failure codes so callers never need to catch
        transport, encryption, ORM, or outbound-policy exceptions.
        """
        endpoint = await Endpoint.filter(id=endpoint_id, account_id=account_id, deleted_at=None).first()
        if endpoint is None:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.NOT_FOUND)
        if not endpoint.enabled:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.DISABLED)
        protocol = EndpointProtocol(endpoint.protocol)
        if not self._request_matches(protocol, request):
            return EndpointAccessFailure(code=EndpointAccessFailureCode.PROTOCOL_MISMATCH)
        try:
            url = decrypt_endpoint_url(endpoint.encrypted_url)
            await self._target_policy.validate_url(url, allowed_schemes=HTTP_OUTBOUND_SCHEMES)
            connection = build_endpoint_connection(endpoint)
        except OutboundTargetError:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.TARGET_REJECTED)
        except (EndpointSecretConfigError, HttpTransportConfigError, ValueError):
            return EndpointAccessFailure(code=EndpointAccessFailureCode.CONFIG_UNAVAILABLE)
        try:
            if isinstance(request, EndpointJsonRpcRequest):
                response = await self._client.request_jsonrpc(
                    connection,
                    request.content,
                    timeout=request.timeout,
                    max_response_bytes=request.max_response_bytes,
                )
            else:
                response = await self._client.request_http_api(
                    connection,
                    request.method,
                    request.path,
                    headers=request.headers,
                    query=request.query,
                    content=request.content,
                    timeout=request.timeout,
                    max_response_bytes=request.max_response_bytes,
                )
        except HttpTransportConfigError:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.INVALID_REQUEST)
        except HttpTransportTimeoutError:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.TIMEOUT)
        except HttpTransportResponseTooLargeError:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.RESPONSE_TOO_LARGE)
        except HttpTransportResponseError:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.RESPONSE_FAILED)
        except HttpTransportError:
            return EndpointAccessFailure(code=EndpointAccessFailureCode.CONNECTION_FAILED)
        return EndpointAccessSuccess(response=_to_response(response))

    @staticmethod
    def _request_matches(protocol: EndpointProtocol, request: EndpointRequest) -> bool:
        if protocol is EndpointProtocol.JSONRPC:
            return isinstance(request, EndpointJsonRpcRequest)
        if protocol is EndpointProtocol.HTTP_API:
            return isinstance(request, EndpointHttpApiRequest)
        return False
