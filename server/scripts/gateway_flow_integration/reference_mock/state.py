import asyncio
from collections.abc import Mapping

from scripts.gateway_flow_integration.reference_mock.model import ReferenceChain

BASE_HEADS: Mapping[ReferenceChain, int] = {
    ReferenceChain.ETHEREUM: 20_000_000,
    ReferenceChain.POLYGON: 60_000_000,
    ReferenceChain.BSC: 40_000_000,
    ReferenceChain.ARBITRUM: 250_000_000,
    ReferenceChain.OPTIMISM: 130_000_000,
    ReferenceChain.BASE: 25_000_000,
    ReferenceChain.SOLANA: 300_000_000,
    ReferenceChain.BITCOIN: 900_000,
    ReferenceChain.LITECOIN: 3_000_000,
    ReferenceChain.TRON: 75_000_000,
}


class HeadBook:
    """Keep one monotonic head per chain for the lifetime of a reference mock."""

    def __init__(self, *, step: int = 0) -> None:
        if step < 0:
            raise ValueError('Reference head step cannot be negative.')
        self._step = step
        self._heads = dict(BASE_HEADS)
        self._lock = asyncio.Lock()

    async def read(self, chain: ReferenceChain, *, tick: bool) -> int:
        async with self._lock:
            if tick:
                self._heads[chain] += self._step
            return self._heads[chain]

    async def advance(self, chain: ReferenceChain, delta: int) -> int:
        if not 1 <= delta <= 1_000_000:
            raise ValueError('Reference head delta must be between 1 and 1000000.')
        async with self._lock:
            self._heads[chain] += delta
            return self._heads[chain]

    async def snapshot(self) -> dict[str, int]:
        async with self._lock:
            return {chain.value: height for chain, height in self._heads.items()}

    async def reset(self) -> dict[str, int]:
        async with self._lock:
            self._heads = dict(BASE_HEADS)
            return {chain.value: height for chain, height in self._heads.items()}
