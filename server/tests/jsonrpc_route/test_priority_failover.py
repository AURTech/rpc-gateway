from collections.abc import Generator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Self
from unittest.mock import MagicMock

import pytest
from app.core.errors import UnavailableError
from app.model.blockchain import Chain, Network
from app.model.endpoint import EndpointProtocol
from app.model.jsonrpc_route import (
    JsonRpcLoadBalanceItem,
    JsonRpcLoadBalanceTargetItem,
    JsonRpcPriorityFailoverItem,
    JsonRpcPriorityFailoverTargetItem,
    JsonRpcRouteItem,
    JsonRpcRouteValues,
    JsonRpcRoutingStrategyItem,
    JsonRpcRoutingStrategyType,
)
from app.orm.endpoint import Endpoint
from app.orm.jsonrpc_route import JsonRpcRouteScope, JsonRpcRouteTarget
from app.services.jsonrpc_route.manager import JsonRpcRouteManager
from app.services.jsonrpc_route.runtime import DatabaseJsonRpcRoutePlanProvider
from pydantic import TypeAdapter, ValidationError
from tortoise.backends.base.client import BaseDBAsyncClient


class _RowsQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def order_by(self, _field: str) -> Self:
        return self

    def select_related(self, _field: str) -> Self:
        return self

    def using_db(self, _connection: BaseDBAsyncClient) -> Self:
        return self

    async def _load(self) -> list[object]:
        return self._rows

    def __await__(self) -> Generator[None, None, list[object]]:
        return self._load().__await__()


def _route(strategy_type: JsonRpcRoutingStrategyType) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id='route-a',
        gateway_id='gateway-a',
        strategy_type=strategy_type,
        max_attempts=3,
        retry_policy='safe_only',
        version=1,
        created_at=now,
        modified_at=now,
    )


def _target(weight: int | None) -> SimpleNamespace:
    endpoint = SimpleNamespace(
        id='endpoint-a',
        account_id='account-a',
        chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        protocol=EndpointProtocol.JSONRPC,
        enabled=True,
        version=1,
    )
    return SimpleNamespace(endpoint_id='endpoint-a', position=0, weight=weight, endpoint=endpoint)


def _patch_rows(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scopes: list[object],
    targets: list[object],
) -> None:
    def scope_filter(**_kwargs: object) -> _RowsQuery:
        return _RowsQuery(scopes)

    def target_filter(**_kwargs: object) -> _RowsQuery:
        return _RowsQuery(targets)

    monkeypatch.setattr(JsonRpcRouteScope, 'filter', scope_filter)
    monkeypatch.setattr(JsonRpcRouteTarget, 'filter', target_filter)


def test_priority_failover_model() -> None:
    params = JsonRpcRouteValues.model_validate(
        {
            'strategy': {
                'type': 'priority_failover',
                'targets': [{'endpoint_id': 'endpoint-a'}, {'endpoint_id': 'endpoint-b'}],
            }
        }
    )

    assert params.strategy.type is JsonRpcRoutingStrategyType.PRIORITY_FAILOVER
    assert [target.endpoint_id for target in params.strategy.targets] == ['endpoint-a', 'endpoint-b']


def test_priority_rejects_weight() -> None:
    with pytest.raises(ValidationError) as exc_info:
        JsonRpcRouteValues.model_validate(
            {
                'strategy': {
                    'type': 'priority_failover',
                    'targets': [{'endpoint_id': 'endpoint-a', 'weight': 100}],
                }
            }
        )

    assert exc_info.value.errors()[0]['type'] == 'extra_forbidden'


def test_priority_rejects_duplicate_endpoints() -> None:
    with pytest.raises(ValidationError, match='cannot contain duplicates'):
        JsonRpcRouteValues.model_validate(
            {
                'strategy': {
                    'type': 'priority_failover',
                    'targets': [{'endpoint_id': 'endpoint-a'}, {'endpoint_id': 'endpoint-a'}],
                }
            }
        )


def test_strategy_response_shapes() -> None:
    strategy_adapter = TypeAdapter(JsonRpcRoutingStrategyItem)
    priority = strategy_adapter.validate_python(
        {
            'type': 'priority_failover',
            'targets': [{'endpoint_id': 'endpoint-a', 'position': 0}],
        }
    )
    load_balance = strategy_adapter.validate_python(
        {
            'type': 'load_balance',
            'targets': [{'endpoint_id': 'endpoint-a', 'position': 0, 'weight': 200}],
        }
    )

    assert isinstance(priority, JsonRpcPriorityFailoverItem)
    assert priority.targets == [JsonRpcPriorityFailoverTargetItem(endpoint_id='endpoint-a', position=0)]
    assert isinstance(load_balance, JsonRpcLoadBalanceItem)
    assert load_balance.targets == [JsonRpcLoadBalanceTargetItem(endpoint_id='endpoint-a', position=0, weight=200)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('strategy', 'expected_weights'),
    [
        (
            {'type': 'priority_failover', 'targets': [{'endpoint_id': 'endpoint-a'}, {'endpoint_id': 'endpoint-b'}]},
            [None, None],
        ),
        (
            {
                'type': 'load_balance',
                'targets': [
                    {'endpoint_id': 'endpoint-a', 'weight': 300},
                    {'endpoint_id': 'endpoint-b', 'weight': 700},
                ],
            },
            [300, 700],
        ),
    ],
)
async def test_strategy_weights(
    monkeypatch: pytest.MonkeyPatch,
    strategy: dict[str, object],
    expected_weights: list[int | None],
) -> None:
    saved: list[JsonRpcRouteTarget] = []

    async def save_rows(
        rows: list[JsonRpcRouteTarget],
        *,
        using_db: BaseDBAsyncClient,
    ) -> None:
        saved.extend(rows)

    monkeypatch.setattr(JsonRpcRouteTarget, 'bulk_create', save_rows)
    params = JsonRpcRouteValues.model_validate({'strategy': strategy})
    endpoints = [Endpoint(id='endpoint-a'), Endpoint(id='endpoint-b')]
    connection = MagicMock(spec=BaseDBAsyncClient)

    await JsonRpcRouteManager._save_targets('route-a', endpoints, params, using_db=connection)

    assert [row.position for row in saved] == [0, 1]
    assert [row.weight for row in saved] == expected_weights


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('strategy_type', 'weight'),
    [
        (JsonRpcRoutingStrategyType.LOAD_BALANCE, 100),
        (JsonRpcRoutingStrategyType.PRIORITY_FAILOVER, None),
    ],
)
async def test_response_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    strategy_type: JsonRpcRoutingStrategyType,
    weight: int | None,
) -> None:
    _patch_rows(monkeypatch, scopes=[SimpleNamespace(method='')], targets=[_target(weight)])

    # Reason: the fake route exposes the exact persisted fields consumed by this mapper.
    item = await JsonRpcRouteManager._to_item(_route(strategy_type))  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]
    reparsed = JsonRpcRouteItem.model_validate(item.model_dump(mode='json'))

    assert reparsed == item
    target = reparsed.model_dump(mode='json')['strategy']['targets'][0]
    assert ('weight' in target) is (strategy_type is JsonRpcRoutingStrategyType.LOAD_BALANCE)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('strategy_type', 'weight'),
    [
        (JsonRpcRoutingStrategyType.LOAD_BALANCE, None),
        (JsonRpcRoutingStrategyType.LOAD_BALANCE, 1001),
        (JsonRpcRoutingStrategyType.PRIORITY_FAILOVER, 100),
    ],
)
async def test_response_rejects_weight(
    monkeypatch: pytest.MonkeyPatch,
    strategy_type: JsonRpcRoutingStrategyType,
    weight: int | None,
) -> None:
    _patch_rows(monkeypatch, scopes=[SimpleNamespace(method='')], targets=[_target(weight)])

    with pytest.raises(UnavailableError):
        # Reason: the fake route exposes the exact persisted fields consumed by this mapper.
        await JsonRpcRouteManager._to_item(
            _route(strategy_type)  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('strategy_type', 'weight'),
    [
        (JsonRpcRoutingStrategyType.LOAD_BALANCE, None),
        (JsonRpcRoutingStrategyType.LOAD_BALANCE, 1001),
        (JsonRpcRoutingStrategyType.PRIORITY_FAILOVER, 100),
    ],
)
async def test_runtime_rejects_weight(
    monkeypatch: pytest.MonkeyPatch,
    strategy_type: JsonRpcRoutingStrategyType,
    weight: int | None,
) -> None:
    route = _route(strategy_type)
    scope = SimpleNamespace(route=route)
    provider = DatabaseJsonRpcRoutePlanProvider()

    async def get_scope(_account_id: str, _gateway_id: str, _method: str) -> SimpleNamespace:
        return scope

    monkeypatch.setattr(provider, '_get_scope', get_scope)
    _patch_rows(monkeypatch, scopes=[], targets=[_target(weight)])

    with pytest.raises(ValueError, match='target weight is invalid'):
        await provider.load(
            account_id='account-a',
            gateway_id='gateway-a',
            chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            method='eth_call',
        )
