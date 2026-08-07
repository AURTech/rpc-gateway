import argparse
from pathlib import Path

import orjson
from app import init_app
from app.services.auth.scope import pat_scopes_for_route
from fastapi.routing import APIRoute

OPENAPI_PATH = Path(__file__).resolve().parents[1] / 'openapi' / 'v2.json'


def build_openapi() -> bytes:
    app = init_app()
    schema = app.openapi()
    paths = schema.get('paths', {})
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        scopes = pat_scopes_for_route(route.name)
        for method in route.methods or set():
            operation = paths.get(route.path, {}).get(method.lower())
            if isinstance(operation, dict):
                if scopes is None:
                    security = operation.get('security')
                    if isinstance(security, list):
                        operation['security'] = [item for item in security if 'PersonalAccessToken' not in item]
                    continue
                operation['x-required-pat-scopes'] = scopes
                if method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                    parameters = operation.setdefault('parameters', [])
                    parameters.append(
                        {
                            'name': 'Idempotency-Key',
                            'in': 'header',
                            'required': False,
                            'description': (
                                'Replays a successful PAT write with the same account, key, and request for 24 hours.'
                            ),
                            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
                        }
                    )
    return orjson.dumps(schema, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b'\n'


def main() -> None:
    parser = argparse.ArgumentParser(description='Export the deterministic management OpenAPI contract.')
    parser.add_argument('--check', action='store_true', help='Fail when the checked-in contract is stale.')
    args = parser.parse_args()
    generated = build_openapi()
    if args.check:
        if not OPENAPI_PATH.is_file() or OPENAPI_PATH.read_bytes() != generated:
            raise SystemExit('OpenAPI contract is stale. Run make openapi.')
        return
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_bytes(generated)


if __name__ == '__main__':
    main()
