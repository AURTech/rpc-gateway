from dataclasses import dataclass

from app.model.jsonrpc_forwarding import JsonRpcForwardingResult


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemJsonRpcCacheResult:
    value: bytes | JsonRpcForwardingResult | None
    eligible: bool
    hit: bool
