import pytest
from app.model.jsonrpc_route import DeleteJsonRpcMethodRouteParams
from pydantic import ValidationError


def test_delete_method_route_params_parse_query_version() -> None:
    params = DeleteJsonRpcMethodRouteParams.model_validate({'expected_version': '2'})

    assert params.expected_version == 2


def test_delete_method_route_params_reject_invalid_version() -> None:
    with pytest.raises(ValidationError):
        DeleteJsonRpcMethodRouteParams.model_validate({'expected_version': '0'})
