import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

import orjson


def digest_json(value: object) -> str:
    encoded = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerExpectation:
    started_sequence: int
    finished_sequence: int
    replica: str
    behavior: str
    chain: str
    source: int
    method: str
    request_id: int
    request_digest: str
    params_digest: str
    status_code: int
    response_digest: str


def jsonrpc_expectation(
    *,
    started_sequence: int,
    finished_sequence: int,
    replica: str,
    behavior: str,
    chain: str,
    source: int,
    request: Mapping[str, object],
    result: object,
) -> LedgerExpectation:
    request_id = request.get('id')
    method = request.get('method')
    if not isinstance(request_id, int) or isinstance(request_id, bool) or not isinstance(method, str):
        raise ValueError('Golden JSON-RPC request is invalid.')
    response = {'jsonrpc': '2.0', 'id': request_id, 'result': result}
    return LedgerExpectation(
        started_sequence=started_sequence,
        finished_sequence=finished_sequence,
        replica=replica,
        behavior=behavior,
        chain=chain,
        source=source,
        method=method,
        request_id=request_id,
        request_digest=digest_json(request),
        params_digest=digest_json(request.get('params')),
        status_code=200,
        response_digest=digest_json(response),
    )
