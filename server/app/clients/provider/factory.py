from app.clients.provider.alchemy import AlchemyProviderAdapter
from app.clients.provider.base import ProviderAdapter
from app.clients.provider.chainstack import ChainstackProviderAdapter
from app.clients.provider.drpc import DrpcProviderAdapter
from app.clients.provider.quicknode import QuicknodeProviderAdapter
from app.clients.provider.tenderly import TenderlyProviderAdapter
from app.clients.transport import HttpTransport
from app.model.provider import ProviderVendor


def build_provider_adapter(vendor: ProviderVendor, transport: HttpTransport) -> ProviderAdapter:
    match vendor:
        case ProviderVendor.ALCHEMY:
            return AlchemyProviderAdapter(transport)
        case ProviderVendor.QUICKNODE:
            return QuicknodeProviderAdapter(transport)
        case ProviderVendor.CHAINSTACK:
            return ChainstackProviderAdapter(transport)
        case ProviderVendor.DRPC:
            return DrpcProviderAdapter(transport)
        case ProviderVendor.TENDERLY:
            return TenderlyProviderAdapter(transport)
