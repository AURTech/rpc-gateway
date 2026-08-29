from dataclasses import dataclass

from app.model.http_api_forwarding import HttpApiForwardingResult


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemHttpApiCacheResult:
    value: HttpApiForwardingResult | None
    eligible: bool
    hit: bool
