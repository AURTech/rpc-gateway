from app.core.response import JsonFallbackResponse


def test_json_fallback_response_serializes_large_int_as_json_number() -> None:
    value = 10**100

    response = JsonFallbackResponse({'result': value})

    body = bytes(response.body).decode()
    assert f'"result":{value}' in body
    assert f'"result":"{value}"' not in body
