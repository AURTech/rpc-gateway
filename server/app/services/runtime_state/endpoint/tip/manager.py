from collections.abc import AsyncIterator
from typing import Final

from fastlog import log
from pydantic import ValidationError

from app.infra import redis
from app.model.blockchain import Chain, Network
from app.model.runtime_state.endpoint.tip import TipObservation
from app.model.runtime_state.tip import Finality, TipUnit, validate_tip_dimension
from app.services.runtime_state.endpoint.tip.store import StoreValue, TipKeys, TipStore
from app.services.runtime_state.endpoint.tip.write import TipWriteResult

TIP_TTL_SECONDS: Final[int] = 60 * 60


def _keys(
    *,
    chain: Chain,
    network: Network,
    unit: TipUnit,
    finality: Finality,
) -> TipKeys:
    slot = f'{{tip|{chain.value}|{network.value}|{unit.value}|{finality.value}}}'
    key_parts = ('runtime_state', 'v2', 'tip', slot)
    return TipKeys(
        values=redis.build_key(*key_parts, 'values'),
        index=redis.build_key(*key_parts, 'index'),
        expiry=redis.build_key(*key_parts, 'expiry'),
    )


def _build_tip(
    value: StoreValue,
    *,
    endpoint_id: str,
    chain: Chain,
    network: Network,
    unit: TipUnit,
    finality: Finality,
) -> TipObservation | None:
    try:
        return TipObservation(
            endpoint_id=endpoint_id,
            endpoint_version=value.version,
            chain=chain,
            network=network,
            unit=unit,
            finality=finality,
            value=value.value,
            observed_at=value.observed_at,
        )
    except ValidationError:
        return None


class TipManager:
    def __init__(self, store: TipStore) -> None:
        self._store = store

    async def record(self, tip: TipObservation) -> TipWriteResult:
        """Record an endpoint observation without applying chain-tip or reorg policy.

        A lower height is valid newer evidence. The result distinguishes a stored or stale observation
        from capacity and future-clock rejections that callers may retry.
        """
        keys = _keys(
            chain=tip.chain,
            network=tip.network,
            unit=tip.unit,
            finality=tip.finality,
        )
        return await self._store.put(
            keys=keys,
            key=tip.endpoint_id,
            value=tip.value,
            version=tip.endpoint_version,
            observed_at=tip.observed_at,
            ttl_seconds=TIP_TTL_SECONDS,
        )

    async def get(
        self,
        *,
        endpoint_id: str,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> TipObservation | None:
        validate_tip_dimension(chain=chain, network=network, unit=unit, finality=finality)
        keys = _keys(
            chain=chain,
            network=network,
            unit=unit,
            finality=finality,
        )
        value = await self._store.get(keys=keys, key=endpoint_id)
        if value is None:
            return None
        tip = _build_tip(
            value,
            endpoint_id=endpoint_id,
            chain=chain,
            network=network,
            unit=unit,
            finality=finality,
        )
        if tip is not None:
            return tip
        if await self._store.delete_value(value=value, keys=keys):
            log.warning(f'Tip observation removed after invalid Redis data | Endpoint:{endpoint_id}')
        return None

    async def iterate(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> AsyncIterator[TipObservation]:
        """Yield endpoint observations without materializing the complete dimension."""
        validate_tip_dimension(chain=chain, network=network, unit=unit, finality=finality)
        keys = _keys(chain=chain, network=network, unit=unit, finality=finality)
        async for value in self._store.iterate(keys):
            endpoint_id = value.key
            tip = _build_tip(
                value,
                endpoint_id=endpoint_id,
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
            )
            if tip is None:
                if await self._store.delete_value(value=value, keys=keys):
                    log.warning(f'Tip observation removed after invalid Redis data | Endpoint:{value.key}')
                continue
            yield tip

    async def list(
        self,
        *,
        chain: Chain,
        network: Network,
        unit: TipUnit,
        finality: Finality,
    ) -> list[TipObservation]:
        return [
            tip
            async for tip in self.iterate(
                chain=chain,
                network=network,
                unit=unit,
                finality=finality,
            )
        ]
