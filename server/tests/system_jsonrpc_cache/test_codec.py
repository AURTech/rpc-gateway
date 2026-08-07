import pytest
from app.services.system_jsonrpc_cache.codec import PayloadCodec


@pytest.mark.anyio
async def test_payload_codec_round_trip_large_result() -> None:
    payload = (b'{"block":' + b'"transaction",' * 800_000) + b'null}'
    codec = PayloadCodec(max_concurrency=2)

    compressed = await codec.compress(payload)
    restored = await codec.decompress(compressed, expected_size=len(payload))

    assert restored == payload
    assert len(compressed) < len(payload)


@pytest.mark.anyio
async def test_payload_codec_rejects_corrupted_frame() -> None:
    codec = PayloadCodec(max_concurrency=1)
    compressed = await codec.compress(b'payload')

    with pytest.raises(ValueError, match='compression frame'):
        await codec.decompress(compressed[:-1] + b'x', expected_size=7)


@pytest.mark.anyio
async def test_payload_codec_rejects_wrong_size() -> None:
    codec = PayloadCodec(max_concurrency=1)
    compressed = await codec.compress(b'payload')

    with pytest.raises(ValueError, match='decompressed size'):
        await codec.decompress(compressed, expected_size=8)
