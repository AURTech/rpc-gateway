import json
from dataclasses import dataclass, field
from typing import Any, Literal, Self

import msgspec
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600


class JsonRpcProtocolError(Exception):
    def __init__(self, code: int, message: str, request_id: str | int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id


class JsonRpcCall(BaseModel):
    model_config = ConfigDict(strict=True, extra='ignore')

    jsonrpc: Literal['2.0']
    method: str = Field(min_length=1, max_length=256)
    params: dict[str, Any] | list[Any] | None = None
    id: str | int | None = None

    @field_validator('id', mode='before')
    @classmethod
    def validate_id(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (str, int, type(None))):
            raise ValueError('JSON-RPC id must be a string, integer, or null.')
        return value

    @model_validator(mode='after')
    def validate_params(self) -> Self:
        if 'params' in self.model_fields_set and self.params is None:
            raise ValueError('JSON-RPC params must be an object or array.')
        return self

    @property
    def is_notification(self) -> bool:
        return 'id' not in self.model_fields_set

    def request_id(self) -> str | int | None:
        return self.id if 'id' in self.model_fields_set else None

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class JsonRpcError(BaseModel):
    model_config = ConfigDict(strict=True, extra='ignore')

    code: int
    message: str
    data: Any = None

    @field_validator('code', mode='before')
    @classmethod
    def validate_code(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError('JSON-RPC error code must be an integer.')
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcSuccessResponse:
    id: str | int | None
    result: bytes
    jsonrpc: Literal['2.0'] = '2.0'


class JsonRpcErrorResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra='ignore')

    jsonrpc: Literal['2.0'] = '2.0'
    id: str | int | None
    error: JsonRpcError


JsonRpcResponse = JsonRpcSuccessResponse | JsonRpcErrorResponse


class _ResponseEnvelope(msgspec.Struct):
    jsonrpc: Any | msgspec.UnsetType = msgspec.UNSET
    id: Any | msgspec.UnsetType = msgspec.UNSET
    result: msgspec.Raw | msgspec.UnsetType = msgspec.UNSET
    error: msgspec.Raw | msgspec.UnsetType = msgspec.UNSET


_RESPONSE_DECODER = msgspec.json.Decoder(_ResponseEnvelope)


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonRpcCallResult:
    response: JsonRpcErrorResponse | None
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    raw_result: bytes | None = None
    request_id: str | int | None = None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f'Invalid JSON constant: {value}')


def _load_json(body: bytes) -> Any:
    try:
        return json.loads(body, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise JsonRpcProtocolError(JSONRPC_PARSE_ERROR, 'Parse error.') from exc


def parse_jsonrpc_call(body: bytes) -> JsonRpcCall:
    payload: object = _load_json(body)
    if not isinstance(payload, dict):
        raise JsonRpcProtocolError(JSONRPC_INVALID_REQUEST, 'Invalid Request.')
    try:
        return JsonRpcCall.model_validate(payload)
    except ValidationError as exc:
        raise JsonRpcProtocolError(JSONRPC_INVALID_REQUEST, 'Invalid Request.') from exc


def _validate_response_id(value: object, request_id: str | int | None) -> str | int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, type(None))) or value != request_id:
        raise ValueError('Endpoint JSON-RPC response id is invalid.')
    return value


def parse_jsonrpc_response(body: bytes, request_id: str | int | None, *, allow_missing_version: bool) -> JsonRpcResponse:
    try:
        payload = _RESPONSE_DECODER.decode(body)
    except (msgspec.DecodeError, RecursionError) as exc:
        raise ValueError('Endpoint returned invalid JSON.') from exc
    version = payload.jsonrpc
    if version != '2.0' and not (allow_missing_version and version is msgspec.UNSET):
        raise ValueError('Endpoint JSON-RPC response version is invalid.')
    if payload.id is msgspec.UNSET:
        raise ValueError('Endpoint JSON-RPC response id is missing.')
    response_id = _validate_response_id(payload.id, request_id)
    result = payload.result
    error_payload = payload.error
    has_result = result is not msgspec.UNSET
    has_error = error_payload is not msgspec.UNSET
    if has_result == has_error:
        raise ValueError('Endpoint JSON-RPC response must include exactly one result or error.')
    try:
        if result is not msgspec.UNSET:
            return JsonRpcSuccessResponse(id=response_id, result=bytes(result))
        if error_payload is msgspec.UNSET:
            raise ValueError('Endpoint JSON-RPC response is invalid.')
        error = JsonRpcError.model_validate_json(bytes(error_payload))
        return JsonRpcErrorResponse(jsonrpc='2.0', id=response_id, error=error)
    except ValidationError as exc:
        raise ValueError('Endpoint JSON-RPC response is invalid.') from exc
