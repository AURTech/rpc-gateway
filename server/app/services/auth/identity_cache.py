from app.infra import redis
from app.model.auth import AuthIdentity
from app.services.base import Manager

AUTH_IDENTITY_TTL_SECONDS = 60


class AuthIdentityCache(Manager):
    @classmethod
    def key(cls, token_hash: str) -> str:
        return redis.build_key('auth', 'identity', 'v4', token_hash)

    @classmethod
    async def get(cls, token_hash: str) -> AuthIdentity | None:
        raw = await cls.redis.get(cls.key(token_hash))
        if raw is None:
            return None
        try:
            return AuthIdentity.model_validate_json(raw)
        except ValueError:
            await cls.redis.delete(cls.key(token_hash))
            return None

    @classmethod
    async def set(cls, token_hash: str, identity: AuthIdentity, *, ttl_seconds: int = AUTH_IDENTITY_TTL_SECONDS) -> None:
        if ttl_seconds <= 0:
            return
        await cls.redis.set(cls.key(token_hash), identity.model_dump_json(), ex=ttl_seconds)

    @classmethod
    async def delete(cls, token_hash: str) -> None:
        await cls.redis.delete(cls.key(token_hash))
