from enum import StrEnum


class ProviderVendor(StrEnum):
    ALCHEMY = 'alchemy'
    QUICKNODE = 'quicknode'
    CHAINSTACK = 'chainstack'
    DRPC = 'drpc'
    TENDERLY = 'tenderly'

    @property
    def label(self) -> str:
        return {
            ProviderVendor.ALCHEMY: 'Alchemy',
            ProviderVendor.QUICKNODE: 'QuickNode',
            ProviderVendor.CHAINSTACK: 'Chainstack',
            ProviderVendor.DRPC: 'dRPC',
            ProviderVendor.TENDERLY: 'Tenderly',
        }[self]


class ProviderSyncStatus(StrEnum):
    NEVER = 'never'
    SUCCESS = 'success'
    PARTIAL = 'partial'
    FAILED = 'failed'


class ProviderEndpointSyncStatus(StrEnum):
    AVAILABLE = 'available'
    MISSING = 'missing'


class ProviderEndpointDiscoveryStatus(StrEnum):
    PRESENT = 'present'
    MISSING = 'missing'


class ProviderSyncTrigger(StrEnum):
    MANUAL = 'manual'
    SCHEDULED = 'scheduled'


class ProviderSyncRunState(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCESS = 'success'
    PARTIAL = 'partial'
    FAILED = 'failed'


class ProviderEndpointAction(StrEnum):
    CREATED = 'created'
    UPDATED = 'updated'
    RESTORED = 'restored'
    ARCHIVED = 'archived'
    SKIPPED = 'skipped'
    FAILED = 'failed'
