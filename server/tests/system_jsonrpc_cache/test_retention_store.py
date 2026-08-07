import pytest
from app.infra.db import SYSTEM_CACHE_RETENTION_DB_CONNECTION
from app.model.blockchain import Chain, Network
from app.services.system_jsonrpc_cache.store import PostgresRetentionStore
from tortoise import connections
from tortoise.transactions import in_transaction

pytestmark = pytest.mark.anyio


async def _insert_payload(*, chain: Chain, cache_key: str, size: int, age_seconds: int) -> None:
    payload = b'x' * size
    connection = connections.get('default')
    await connection.execute_query(
        """
        INSERT INTO system_jsonrpc_cache_payload (
            chain, network, method, cache_key, sequence, payload, payload_size, stored_size,
            fresh_until, stale_until, publisher_fence, stored_at
        )
        VALUES ($1, $2, 'debug_traceBlockByNumber', $3, 1, $4, $5, $5, NULL, NULL, 0,
                NOW() - ($6::bigint * INTERVAL '1 second'))
        """,
        [chain.value, Network.MAINNET.value, cache_key, payload, size, age_seconds],
    )


async def _insert_orphan_lease(*, cache_key: str, age_seconds: int) -> None:
    connection = connections.get('default')
    await connection.execute_query(
        """
        INSERT INTO system_jsonrpc_cache_payload_lease (
            chain, network, method, cache_key, token, fence, lease_until
        )
        VALUES ($1, $2, 'debug_traceBlockByNumber', $3, 'expired-token', 1, NOW() - ($4::bigint * INTERVAL '1 second'))
        """,
        [Chain.ETHEREUM.value, Network.MAINNET.value, cache_key, age_seconds],
    )


async def _remaining_payload_keys(chain: Chain) -> list[str]:
    connection = connections.get('default')
    rows = await connection.execute_query_dict(
        """
        SELECT cache_key
        FROM system_jsonrpc_cache_payload
        WHERE chain = $1
        ORDER BY stored_at, id
        """,
        [chain.value],
    )
    return [str(row['cache_key']) for row in rows]


async def _remaining_lease_keys() -> list[str]:
    connection = connections.get('default')
    rows = await connection.execute_query_dict(
        """
        SELECT cache_key
        FROM system_jsonrpc_cache_payload_lease
        ORDER BY lease_until, id
        """
    )
    return [str(row['cache_key']) for row in rows]


async def test_retention_cleanup_bounds_rows_and_bytes(orm_schema: None) -> None:
    del orm_schema
    keys = [f'{index:040d}' for index in range(1, 9)]
    for key, age_seconds in zip(keys[:3], (7203, 7202, 7201), strict=True):
        await _insert_payload(chain=Chain.ETHEREUM, cache_key=key, size=6, age_seconds=age_seconds)
    await _insert_payload(chain=Chain.ETHEREUM, cache_key=keys[3], size=1, age_seconds=30)
    await _insert_payload(chain=Chain.ARBITRUM, cache_key=keys[4], size=1, age_seconds=7200)
    store = PostgresRetentionStore()

    first = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=64, max_bytes=10)
    assert (first.deleted_rows, first.deleted_bytes, first.has_more) == (1, 6, True)
    assert await _remaining_payload_keys(Chain.ETHEREUM) == keys[1:4]

    second = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=64, max_bytes=10)
    third = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=64, max_bytes=10)
    assert (second.deleted_rows, second.deleted_bytes, second.has_more) == (1, 6, True)
    assert (third.deleted_rows, third.deleted_bytes, third.has_more) == (1, 6, False)
    assert await _remaining_payload_keys(Chain.ETHEREUM) == [keys[3]]
    assert await _remaining_payload_keys(Chain.ARBITRUM) == [keys[4]]

    await _insert_payload(chain=Chain.ETHEREUM, cache_key=keys[5], size=12, age_seconds=7202)
    await _insert_payload(chain=Chain.ETHEREUM, cache_key=keys[6], size=4, age_seconds=7201)
    oversized = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=64, max_bytes=10)
    assert (oversized.deleted_rows, oversized.deleted_bytes, oversized.has_more) == (1, 12, True)

    await _insert_payload(chain=Chain.ETHEREUM, cache_key=keys[7], size=4, age_seconds=7200)
    row_bounded = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=1, max_bytes=10)
    assert (row_bounded.deleted_rows, row_bounded.deleted_bytes, row_bounded.has_more) == (1, 4, True)


async def test_orphan_lease_cleanup_reports_more_work(orm_schema: None) -> None:
    del orm_schema
    keys = [f'{index:040d}' for index in range(1, 4)]
    for key, age_seconds in zip(keys, (7203, 7202, 7201), strict=True):
        await _insert_orphan_lease(cache_key=key, age_seconds=age_seconds)
    store = PostgresRetentionStore()

    first = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=2, max_bytes=10)
    second = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=2, max_bytes=10)

    assert (first.deleted_rows, first.deleted_bytes, first.has_more) == (0, 0, True)
    assert (second.deleted_rows, second.deleted_bytes, second.has_more) == (0, 0, False)
    connection = connections.get('default')
    rows = await connection.execute_query_dict('SELECT id FROM system_jsonrpc_cache_payload_lease')
    assert not rows


async def test_orphan_lease_cleanup_skips_renewal_and_fills_batch(orm_schema: None) -> None:
    del orm_schema
    renewed_key = f'{1:040d}'
    expired_key = f'{2:040d}'
    await _insert_orphan_lease(cache_key=renewed_key, age_seconds=7201)
    await _insert_orphan_lease(cache_key=expired_key, age_seconds=7200)
    store = PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)

    async with in_transaction(connection_name='default') as transaction:
        await transaction.execute_query(
            """
            UPDATE system_jsonrpc_cache_payload_lease
            SET lease_until = clock_timestamp() + INTERVAL '1 hour'
            WHERE cache_key = $1
            """,
            [renewed_key],
        )
        result = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=1, max_bytes=10)

    assert (result.deleted_rows, result.deleted_bytes, result.has_more) == (0, 0, True)
    assert await _remaining_lease_keys() == [renewed_key]

    drained = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=1, max_bytes=10)
    assert (drained.deleted_rows, drained.deleted_bytes, drained.has_more) == (0, 0, False)
    assert await _remaining_lease_keys() == [renewed_key]


async def test_locked_retention_row_is_skipped_and_reported_as_pending(orm_schema: None) -> None:
    del orm_schema
    key = f'{1:040d}'
    await _insert_payload(chain=Chain.ETHEREUM, cache_key=key, size=4, age_seconds=7200)
    store = PostgresRetentionStore(SYSTEM_CACHE_RETENTION_DB_CONNECTION)

    async with in_transaction(connection_name='default') as transaction:
        await transaction.execute_query(
            'SELECT id FROM system_jsonrpc_cache_payload WHERE cache_key = $1 FOR UPDATE',
            [key],
        )
        skipped = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=1, max_bytes=10)

    assert (skipped.deleted_rows, skipped.deleted_bytes, skipped.has_more) == (0, 0, True)
    deleted = await store.delete_expired(Chain.ETHEREUM, 3600, max_rows=1, max_bytes=10)
    assert (deleted.deleted_rows, deleted.deleted_bytes, deleted.has_more) == (1, 4, False)
