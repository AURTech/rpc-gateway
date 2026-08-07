import pytest
from app.model.public import JsonRpcErrorResponse, JsonRpcSuccessResponse, parse_jsonrpc_response


def test_success_result_remains_raw_json() -> None:
    body = b'{"jsonrpc":"2.0","id":1,"result": { "number": 1e2, "items": [1, 2] },"extra":true}'

    response = parse_jsonrpc_response(body, 1, allow_missing_version=False)

    assert isinstance(response, JsonRpcSuccessResponse)
    assert response.result == b'{ "number": 1e2, "items": [1, 2] }'


def test_error_response_uses_validated_error_model() -> None:
    body = b'{"jsonrpc":"2.0","id":"request","error":{"code":-1,"message":"bad","extra":true}}'

    response = parse_jsonrpc_response(body, 'request', allow_missing_version=False)

    assert isinstance(response, JsonRpcErrorResponse)
    assert response.error.code == -1
    assert response.error.message == 'bad'


def test_missing_version_is_allowed_only_for_selected_protocols() -> None:
    body = b'{"id":1,"result":null}'

    response = parse_jsonrpc_response(body, 1, allow_missing_version=True)

    assert isinstance(response, JsonRpcSuccessResponse)
    assert response.result == b'null'
    with pytest.raises(ValueError):
        parse_jsonrpc_response(body, 1, allow_missing_version=False)


@pytest.mark.parametrize(
    ('body', 'request_id'),
    [
        (b'[]', 1),
        (b'{"jsonrpc":"1.0","id":1,"result":null}', 1),
        (b'{"jsonrpc":"2.0","result":null}', 1),
        (b'{"jsonrpc":"2.0","id":true,"result":null}', True),
        (b'{"jsonrpc":"2.0","id":2,"result":null}', 1),
        (b'{"jsonrpc":"2.0","id":1}', 1),
        (b'{"jsonrpc":"2.0","id":1,"result":null,"error":null}', 1),
        (b'{"jsonrpc":"2.0","id":1,"result":NaN}', 1),
        (b'{"jsonrpc":"2.0","id":1,"result":Infinity}', 1),
        (b'{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"bad","data":NaN}}', 1),
        (b'\xff', 1),
    ],
)
def test_invalid_response_contract_is_rejected(body: bytes, request_id: str | int | None) -> None:
    with pytest.raises(ValueError):
        parse_jsonrpc_response(body, request_id, allow_missing_version=False)


def test_huge_integer_id_is_preserved() -> None:
    request_id = 10**100
    body = f'{{"jsonrpc":"2.0","id":{request_id},"result":"ok"}}'.encode()

    response = parse_jsonrpc_response(body, request_id, allow_missing_version=False)

    assert isinstance(response, JsonRpcSuccessResponse)
    assert response.id == request_id


def test_large_nested_result_is_returned_as_bytes() -> None:
    raw_result = b'[{"values":[' + b','.join([b'123456789'] * 100_000) + b']}]'
    body = b'{"jsonrpc":"2.0","id":1,"result":' + raw_result + b'}'

    response = parse_jsonrpc_response(body, 1, allow_missing_version=False)

    assert isinstance(response, JsonRpcSuccessResponse)
    assert response.result == raw_result
