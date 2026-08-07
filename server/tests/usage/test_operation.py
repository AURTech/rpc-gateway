from app.services.usage.operation import normalize_http_operation


def test_normalizes_wallet_operation_without_dynamic_values() -> None:
    assert normalize_http_operation('post', '/wallet/getnowblock') == 'POST /wallet/getnowblock'
    assert normalize_http_operation('POST', '/wallet/getaccount/address') == 'POST /wallet/getaccount/{id}'


def test_normalizes_trongrid_resource_identifiers() -> None:
    operation = normalize_http_operation('get', '/v1/accounts/TAddress/transactions/trc20')

    assert operation == 'GET /v1/accounts/{id}/transactions/trc20'
    assert 'TAddress' not in operation


def test_rejects_unknown_http_operation_family() -> None:
    assert normalize_http_operation('GET', '/unknown/path') == '__other__'
    assert normalize_http_operation('GET', '/v1/private-value/identifier') == 'GET /v1/__other__'
