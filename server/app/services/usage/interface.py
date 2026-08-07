from typing import Protocol

from app.model.usage import GatewayUsageEvent


class GatewayUsage(Protocol):
    def submit(self, event: GatewayUsageEvent) -> bool: ...
