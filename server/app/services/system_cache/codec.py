from anyio import CapacityLimiter, to_thread
from zstandard import ZstdCompressor, ZstdDecompressor, ZstdError


class PayloadCodec:
    """Compress cache payloads outside the event loop with bounded CPU concurrency."""

    def __init__(self, *, max_concurrency: int = 4) -> None:
        if max_concurrency < 1:
            raise ValueError('Payload codec concurrency must be positive.')
        self._limiter = CapacityLimiter(max_concurrency)

    async def compress(self, payload: bytes) -> bytes:
        return await to_thread.run_sync(_compress, payload, limiter=self._limiter)

    async def decompress(self, payload: bytes, *, expected_size: int) -> bytes:
        if expected_size < 0:
            raise ValueError('Payload cache size cannot be negative.')
        raw = await to_thread.run_sync(_decompress, payload, expected_size, limiter=self._limiter)
        if len(raw) != expected_size:
            raise ValueError('Payload cache decompressed size is invalid.')
        return raw


def _compress(payload: bytes) -> bytes:
    compressor = ZstdCompressor(level=1, write_checksum=True, write_content_size=True)
    return compressor.compress(payload)


def _decompress(payload: bytes, expected_size: int) -> bytes:
    try:
        return ZstdDecompressor().decompress(payload, max_output_size=expected_size)
    except ZstdError as exc:
        raise ValueError('Payload cache compression frame is invalid.') from exc
