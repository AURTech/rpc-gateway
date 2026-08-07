from enum import StrEnum

from pydantic import BaseModel, Field


class RpcMethodFamily(StrEnum):
    """Chain protocol family a JSON-RPC method catalog is grouped by."""

    EVM = 'evm'
    SVM = 'svm'
    UTXO = 'utxo'
    TRON = 'tron'


class RpcMethodRisk(StrEnum):
    READ = 'read'
    WRITE = 'write'
    SENSITIVE = 'sensitive'

    @property
    def label(self) -> str:
        match self:
            case RpcMethodRisk.READ:
                return 'Read'
            case RpcMethodRisk.WRITE:
                return 'Write'
            case RpcMethodRisk.SENSITIVE:
                return 'Sensitive'


class RpcMethodSource(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., min_length=1, max_length=512)


class RpcMethodItem(BaseModel):
    value: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=128)
    namespace: str = Field(..., min_length=1, max_length=64)
    namespace_label: str = Field(..., min_length=1, max_length=128)
    risk: RpcMethodRisk
    risk_label: str = Field(..., min_length=1, max_length=64)
    deprecated: bool = False


class RpcMethodProtocolGroup(BaseModel):
    protocol: RpcMethodFamily
    protocol_label: str = Field(..., min_length=1, max_length=64)
    sources: list[RpcMethodSource]
    methods: list[RpcMethodItem]


class RpcMethodCatalog(BaseModel):
    items: list[RpcMethodProtocolGroup]
