import re
from typing import Final

import msgspec

from app.model.public.jsonrpc import JsonRpcCall, JsonRpcSuccessResponse

_HEX_QUANTITY: Final[re.Pattern[str]] = re.compile(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)')
_MAX_HEX_DIGITS: Final[int] = 64
_MAX_HEX_LENGTH: Final[int] = 2 + _MAX_HEX_DIGITS
_MAX_UINT64: Final[int] = (1 << 64) - 1
_UINT_DECODER = msgspec.json.Decoder(int)
_STRING_DECODER = msgspec.json.Decoder(str)


def matches_call(call: JsonRpcCall, response: JsonRpcSuccessResponse) -> bool:
    return not call.is_notification and response.id == call.request_id()


def parse_uint(raw_result: bytes) -> int | None:
    try:
        value = _UINT_DECODER.decode(raw_result)
    except msgspec.DecodeError:
        return None
    if not 0 <= value <= _MAX_UINT64:
        return None
    return value


def parse_hex_quantity(raw_result: bytes) -> int | None:
    try:
        value = _STRING_DECODER.decode(raw_result)
    except msgspec.DecodeError:
        return None
    if not 3 <= len(value) <= _MAX_HEX_LENGTH or not value.isascii():
        return None
    if _HEX_QUANTITY.fullmatch(value) is None:
        return None
    return int(value[2:], 16)
