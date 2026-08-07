from hmac import compare_digest

from app.model.public import (
    PublicAccessFailure,
    PublicAccessFailureCode,
    PublicGatewayAddress,
    PublicGatewayContext,
    PublicGatewayIdentity,
)
from app.model.transport import Transport
from app.services.gateway.host import parse_gateway_host
from app.services.public.lookup import PublicGatewayLookup, PublicIdentityLookup, PublicLookupFailure


def _bearer_key(value: str | None) -> str | None:
    if value is None:
        return None
    parts = value.strip().split()
    if len(parts) != 2 or parts[0].casefold() != 'bearer':
        return None
    return parts[1]


def _select_api_key(path_key: str | None, authorization: str | None) -> str | None:
    header_key = _bearer_key(authorization)
    if authorization is not None and header_key is None:
        return None
    if path_key is None:
        return header_key
    if header_key is not None and not compare_digest(path_key, header_key):
        return None
    return path_key


class PublicGatewayAccessManager:
    def __init__(
        self,
        identities: PublicIdentityLookup,
        gateways: PublicGatewayLookup,
    ) -> None:
        self._identities = identities
        self._gateways = gateways

    @staticmethod
    def match_host(host: str | None, transport: Transport) -> PublicGatewayAddress | None:
        try:
            chain, network = parse_gateway_host(host, transport)
        except ValueError:
            return None
        return PublicGatewayAddress(chain=chain, network=network, transport=transport)

    async def authenticate(
        self,
        path_key: str | None,
        authorization: str | None,
    ) -> PublicGatewayIdentity | PublicAccessFailure:
        api_key = _select_api_key(path_key, authorization)
        if api_key is None:
            return PublicAccessFailure(code=PublicAccessFailureCode.AUTHENTICATION_FAILED)
        try:
            identity = await self._identities.find(api_key)
        except Exception:
            return PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
        if isinstance(identity, PublicLookupFailure):
            return PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
        if identity is None:
            return PublicAccessFailure(code=PublicAccessFailureCode.AUTHENTICATION_FAILED)
        return identity

    async def get_context(
        self,
        address: PublicGatewayAddress,
        identity: PublicGatewayIdentity,
    ) -> PublicGatewayContext | PublicAccessFailure:
        try:
            gateway = await self._gateways.find(
                app_id=identity.app_id,
                chain=address.chain,
                network=address.network,
            )
        except Exception:
            return PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
        if isinstance(gateway, PublicLookupFailure):
            return PublicAccessFailure(code=PublicAccessFailureCode.INTERNAL)
        if gateway is None:
            return PublicAccessFailure(code=PublicAccessFailureCode.GATEWAY_NOT_FOUND)
        if not gateway.enabled:
            return PublicAccessFailure(code=PublicAccessFailureCode.GATEWAY_DISABLED)
        if address.transport not in gateway.transports:
            return PublicAccessFailure(code=PublicAccessFailureCode.GATEWAY_NOT_FOUND)
        return PublicGatewayContext(
            account_id=identity.account_id,
            account_role=identity.account_role,
            app_id=identity.app_id,
            gateway_id=gateway.gateway_id,
            chain=address.chain,
            network=address.network,
            transport=address.transport,
        )
