from dataclasses import replace

import orjson
from scripts.gateway_flow_integration.reference_mock.fixtures import build_result
from scripts.gateway_flow_integration.reference_mock.model import (
    JsonValue,
    ReferenceBehavior,
    ReferenceReply,
    ReferenceTransport,
    RequestFacts,
)


def _jsonrpc_payload(facts: RequestFacts, result: JsonValue, response_id: str | int | None) -> JsonValue:
    return {'jsonrpc': '2.0', 'id': response_id, 'result': result}


def _encoded_reply(facts: RequestFacts, result: JsonValue, response_id: str | int | None) -> ReferenceReply:
    payload = _jsonrpc_payload(facts, result, response_id) if facts.transport is ReferenceTransport.JSONRPC else result
    return ReferenceReply(
        status_code=200,
        body=orjson.dumps(payload),
        media_type='application/json',
        response_id=response_id,
        payload=payload,
    )


def build_reply(facts: RequestFacts, behavior: ReferenceBehavior) -> ReferenceReply:
    if behavior in {ReferenceBehavior.BAD, ReferenceBehavior.UNAVAILABLE}:
        return ReferenceReply(
            status_code=503,
            body=b'reference upstream unavailable',
            media_type='text/plain',
            response_id=None,
            payload=None,
        )
    if behavior is ReferenceBehavior.INVALID:
        return ReferenceReply(
            status_code=200,
            body=b'not-json',
            media_type='text/plain',
            response_id=None,
            payload=None,
        )
    response_id = facts.request_id
    if behavior is ReferenceBehavior.WRONG_ID and facts.transport is ReferenceTransport.JSONRPC:
        response_id = f'wrong-{facts.request_id}'
    result_facts = facts
    if behavior is ReferenceBehavior.WRONG_HEIGHT:
        result_facts = replace(facts, head=facts.head + 1, target_height=facts.target_height + 1)
    result = build_result(result_facts)
    return _encoded_reply(facts, result, response_id)
