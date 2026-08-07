from typing import Annotated

from fastapi import Depends, Query, status

from app.api import BaseRouter, DashRouter
from app.api.deps import AdminIdentityDep, get_admin_identity
from app.model.account import (
    AccountArchiveResult,
    AccountBase,
    AccountDetail,
    AccountList,
    AdminAccountListParams,
    ArchiveAccountsParams,
    CreateAccountParams,
    UpdateAccountStatusParams,
)
from app.services.account import AccountManager

router = BaseRouter(prefix='/accounts', route_class=DashRouter)


@router.post('', response_model=AccountBase, status_code=status.HTTP_201_CREATED)
async def create_account(admin: AdminIdentityDep, params: CreateAccountParams) -> AccountBase:
    """Create an account with the user role."""
    return await AccountManager.create_account(params, actor_id=admin.id)


@router.get('', response_model=AccountList, dependencies=[Depends(get_admin_identity)])
async def list_accounts(
    params: Annotated[AdminAccountListParams, Query()],
) -> AccountList:
    """List user-role accounts.

    search: Case-insensitive partial match on account email.
    status: Filter by account status.
    activated: filter by whether the account has logged in.
    start_at: filter by created_at lower bound, inclusive; timezone-aware and normalized to UTC.
    end_at: filter by created_at upper bound, exclusive; timezone-aware and normalized to UTC.
    sort: created_at sort direction, ASC or DESC.
    page: page number, starting from 1.
    size: page size.
    """
    return await AccountManager.list_accounts(
        search=params.search,
        status=params.status,
        activated=params.activated,
        start_at=params.start_at,
        end_at=params.end_at,
        sort=params.sort,
        page=params.page,
        size=params.size,
    )


@router.post('/delete', response_model=AccountArchiveResult)
async def archive_accounts(admin: AdminIdentityDep, params: ArchiveAccountsParams) -> AccountArchiveResult:
    """Archive one or more user-role accounts.

    ids: account ids to archive.
    """
    return await AccountManager.archive_accounts(params, actor_id=admin.id)


@router.get('/{account_id}', response_model=AccountDetail, dependencies=[Depends(get_admin_identity)])
async def get_account(account_id: str) -> AccountDetail:
    """Return one user-role account with derived counts."""
    return await AccountManager.get_account_detail(account_id)


@router.post('/{account_id}', response_model=AccountBase)
async def update_account(admin: AdminIdentityDep, account_id: str, params: UpdateAccountStatusParams) -> AccountBase:
    """Update one user-role account status.

    status: New account status.
    """
    return await AccountManager.update_account_status(account_id, params, actor_id=admin.id)
