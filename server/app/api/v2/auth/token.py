from typing import Annotated

from fastapi import Query, status

from app.api import BaseRouter, DashRouter
from app.api.deps import SessionIdentityDep
from app.model.auth import (
    CreatedPersonalAccessToken,
    CreatePersonalAccessTokenParams,
    PersonalAccessTokenList,
    PersonalAccessTokenListParams,
    RevokedPersonalAccessToken,
)
from app.services.auth import PersonalAccessTokenManager

router = BaseRouter(prefix='/personal-access-tokens', route_class=DashRouter)


@router.post('', response_model=CreatedPersonalAccessToken, status_code=status.HTTP_201_CREATED)
async def create_personal_access_token(
    identity: SessionIdentityDep,
    params: CreatePersonalAccessTokenParams,
) -> CreatedPersonalAccessToken:
    """Create a scoped personal access token and reveal its secret once."""
    return await PersonalAccessTokenManager.create(identity, params)


@router.get('', response_model=PersonalAccessTokenList)
async def list_personal_access_tokens(
    identity: SessionIdentityDep,
    params: Annotated[PersonalAccessTokenListParams, Query()],
) -> PersonalAccessTokenList:
    """List personal access token metadata without returning token secrets."""
    return await PersonalAccessTokenManager.list(
        identity.id,
        page=params.page,
        size=params.size,
        state=params.state,
    )


@router.delete('/{token_id}', response_model=RevokedPersonalAccessToken)
async def revoke_personal_access_token(
    identity: SessionIdentityDep,
    token_id: str,
) -> RevokedPersonalAccessToken:
    """Revoke an owned personal access token idempotently."""
    return await PersonalAccessTokenManager.revoke(identity.id, token_id)
