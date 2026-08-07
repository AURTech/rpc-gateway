import base64
import contextlib
import hashlib
import re
from dataclasses import dataclass

import orjson
from fastapi import Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import BadRequestError, ConflictError, UnavailableError
from app.infra.redis import RedisLease, acquire_redis_lease, build_key
from app.services.auth.scope import validate_pat_scopes
from app.services.auth.token import PAT_PREFIX, PersonalAccessTokenManager

IDEMPOTENCY_HEADER = 'Idempotency-Key'
IDEMPOTENCY_REPLAY_HEADER = 'Idempotency-Replayed'
IDEMPOTENCY_TTL_SECONDS = 86_400
IDEMPOTENCY_LOCK_SECONDS = 600
_IDEMPOTENCY_KEY_RE = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')


@dataclass(frozen=True, slots=True)
class IdempotencyReplay:
    status_code: int
    body: bytes
    content_type: str
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class IdempotencyExecution:
    redis: Redis
    result_key: str
    fingerprint: str
    lease: RedisLease


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get('authorization', '')
    scheme, separator, token = authorization.partition(' ')
    if separator and scheme.lower() == 'bearer' and token.startswith(PAT_PREFIX):
        return token
    return None


async def _fingerprint(request: Request) -> str:
    body = await request.body()
    digest = hashlib.sha256()
    digest.update(request.method.encode())
    digest.update(b'\0')
    digest.update(request.url.path.encode())
    digest.update(b'\0')
    digest.update(request.url.query.encode())
    digest.update(b'\0')
    digest.update(body)
    return digest.hexdigest()


def _parse_replay(value: str, fingerprint: str) -> IdempotencyReplay:
    try:
        payload = orjson.loads(value)
        if payload['fingerprint'] != fingerprint:
            raise ConflictError(
                'Idempotency key was already used for a different request.',
                code='idempotency.conflict',
            )
        return IdempotencyReplay(
            status_code=int(payload['status_code']),
            body=base64.b64decode(payload['body'], validate=True),
            content_type=str(payload['content_type']),
            headers={str(name): str(header_value) for name, header_value in payload.get('headers', {}).items()},
        )
    except ConflictError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise UnavailableError('Idempotency result is unavailable.', code='idempotency.unavailable') from exc


async def begin_idempotent_request(request: Request) -> IdempotencyReplay | IdempotencyExecution | None:
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    key = request.headers.get(IDEMPOTENCY_HEADER)
    raw_token = _bearer_token(request)
    if key is None or raw_token is None:
        return None
    if not _IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise BadRequestError(
            'Idempotency-Key must contain 1 to 128 safe ASCII characters.',
            code='idempotency.invalid_key',
        )

    identity = await PersonalAccessTokenManager.authenticate(raw_token)
    validate_pat_scopes(request, identity)
    pat_id = identity.pat_id
    if pat_id is None:
        raise UnavailableError('Idempotency identity is unavailable.', code='idempotency.unavailable')
    request.state.pat_id = pat_id
    fingerprint = await _fingerprint(request)
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    result_key = build_key('idempotency', pat_id, key_digest)
    redis: Redis = request.app.state.redis
    lease: RedisLease | None = None
    try:
        cached = await redis.get(result_key)
        if isinstance(cached, str):
            return _parse_replay(cached, fingerprint)

        lock_key = build_key('idempotency-lock', pat_id, key_digest)
        lease = await acquire_redis_lease(redis, lock_key, ttl_seconds=IDEMPOTENCY_LOCK_SECONDS)
        if lease is None:
            raise ConflictError(
                'An idempotent request with this key is still running.',
                code='idempotency.in_progress',
            )
        cached = await redis.get(result_key)
        if isinstance(cached, str):
            await lease.release()
            return _parse_replay(cached, fingerprint)
    except RedisError as exc:
        if lease is not None:
            with contextlib.suppress(RedisError):
                await lease.release()
        raise UnavailableError('Idempotency storage is unavailable.', code='idempotency.unavailable') from exc
    if lease is None:
        raise UnavailableError('Idempotency storage is unavailable.', code='idempotency.unavailable')
    return IdempotencyExecution(redis=redis, result_key=result_key, fingerprint=fingerprint, lease=lease)


async def save_idempotent_response(execution: IdempotencyExecution, response: Response) -> None:
    try:
        if 200 <= response.status_code < 400:
            content_type = response.headers.get('content-type', 'application/json')
            payload = orjson.dumps(
                {
                    'fingerprint': execution.fingerprint,
                    'status_code': response.status_code,
                    'body': base64.b64encode(response.body).decode(),
                    'content_type': content_type,
                    'headers': {
                        name: response.headers[name]
                        for name in ('cache-control', 'pragma', 'expires', 'location')
                        if name in response.headers
                    },
                }
            ).decode()
            await execution.redis.set(execution.result_key, payload, ex=IDEMPOTENCY_TTL_SECONDS)
    except RedisError as exc:
        raise UnavailableError('Idempotency storage is unavailable.', code='idempotency.unavailable') from exc
    finally:
        with contextlib.suppress(RedisError):
            await execution.lease.release()


def replay_response(replay: IdempotencyReplay) -> Response:
    headers = {**replay.headers, IDEMPOTENCY_REPLAY_HEADER: 'true'}
    return Response(
        content=replay.body,
        status_code=replay.status_code,
        media_type=replay.content_type.split(';', 1)[0],
        headers=headers,
    )
