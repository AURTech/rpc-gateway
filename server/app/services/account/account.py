from datetime import UTC, datetime

from fastlog import log
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError
from tortoise.functions import Count

from app.core.errors import BadRequestError, NotfoundError
from app.infra.db import in_tx
from app.model.account import (
    AccountArchiveResult,
    AccountBase,
    AccountDetail,
    AccountList,
    AccountRole,
    AccountStatus,
    ArchiveAccountsParams,
    CreateAccountParams,
    UpdateAccountStatusParams,
)
from app.model.pagination import DEFAULT_LIST_PAGE_SIZE, ListSort, get_created_at_order
from app.orm.account.account import Account
from app.orm.application import App
from app.orm.auth import Auth, AuthSession
from app.orm.gateway import Gateway


class AccountManager:
    @staticmethod
    async def create_account(params: CreateAccountParams, actor_id: str | None = None) -> AccountBase:
        """Create an unactivated user-role account.

        Raises:
            BadRequestError: account email already exists.
        """
        try:
            account = await Account.create(email=params.email, role=AccountRole.USER)
        except IntegrityError as exc:
            log.warning(f'Email already exists | Actor:{actor_id}')
            raise BadRequestError('Account email already exists.') from exc
        log.info(f'Account {account.id} created | Actor:{actor_id}')
        return AccountManager._to_base_response(account)

    @staticmethod
    async def list_accounts(
        search: str | None = None,
        status: AccountStatus | None = None,
        activated: bool | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        sort: ListSort = 'DESC',
        page: int = 1,
        size: int = DEFAULT_LIST_PAGE_SIZE,
    ) -> AccountList:
        """List non-archived user-role accounts.

        Soft-deleted rows are excluded from the result set.
        """
        query = Account.filter(role=AccountRole.USER, deleted_at=None).exclude(status=AccountStatus.ARCHIVED)
        if search:
            query = query.filter(email__icontains=search.strip().lower())
        if status:
            query = query.filter(status=status)
        if activated is True:
            query = query.exclude(first_login_at=None)
        elif activated is False:
            query = query.filter(first_login_at=None)
        if start_at is not None:
            query = query.filter(created_at__gte=start_at)
        if end_at is not None:
            query = query.filter(created_at__lt=end_at)
        total = await query.count()
        order_fields = get_created_at_order(sort)
        rows = await query.order_by(*order_fields).offset((page - 1) * size).limit(size)
        max_page = (total + size - 1) // size
        items = [AccountManager._to_base_response(row) for row in rows]
        return AccountList(
            page=page,
            size=size,
            total=total,
            max_page=max_page,
            items=items,
        )

    @classmethod
    async def get_account_detail(cls, account_id: str) -> AccountDetail:
        """Return one user-role account with derived resource counts.

        Raises:
            NotfoundError: account does not exist.
        """
        account = await cls._get_account(account_id, include_archived=True)
        gateway_count = await Gateway.filter(app__account_id=account.id, app__deleted_at=None, deleted_at=None).count()
        app_count = await App.filter(account_id=account.id, deleted_at=None).count()
        return cls._to_detail_response(account, gateway_count=gateway_count, app_count=app_count)

    @classmethod
    async def update_account_status(
        cls,
        account_id: str,
        params: UpdateAccountStatusParams,
        actor_id: str | None = None,
    ) -> AccountBase:
        """Update one active or disabled user-role account status.

        Raises:
            BadRequestError: archived account cannot be updated.
            NotfoundError: account does not exist.

        Side effects:
            Revokes sessions when disabling an account.
        """
        async with in_tx() as connection:
            account = await (
                Account.select_for_update(using_db=connection)
                .filter(id=account_id, role=AccountRole.USER, deleted_at=None)
                .exclude(status=AccountStatus.ARCHIVED)
                .first()
            )
            if account is None:
                raise NotfoundError('Account not found.')
            old_status = AccountStatus(account.status)
            new_status = params.status
            now = datetime.now(UTC)
            account.status = new_status
            account.modified_at = now
            await account.save(using_db=connection, update_fields=('status', 'modified_at'))
            revoked_session_count = 0
            if new_status is AccountStatus.DISABLED:
                revoked_session_count = await cls._revoke_account_sessions(
                    account.id,
                    revoked_at=now,
                    using_db=connection,
                )
        log.info(
            f'Account status updated | Account:{account.id} | Status:{old_status.value}->{new_status.value} | '
            f'Actor:{actor_id} | RevokedSessions:{revoked_session_count}'
        )
        return cls._to_base_response(account)

    @classmethod
    async def archive_accounts(cls, params: ArchiveAccountsParams, actor_id: str | None = None) -> AccountArchiveResult:
        """Archive one or more user-role accounts.

        Raises:
            NotfoundError: any account does not exist.

        Side effects:
            Releases unique identity fields and revokes sessions.
        """
        async with in_tx() as connection:
            query = Account.select_for_update(using_db=connection).filter(
                id__in=params.ids,
                role=AccountRole.USER,
                deleted_at=None,
            )
            rows = await query.exclude(status=AccountStatus.ARCHIVED).order_by('id')
            rows_by_id = {row.id: row for row in rows}
            missing_ids = [account_id for account_id in params.ids if account_id not in rows_by_id]
            if missing_ids:
                log.warning(f'Account not found | Account:{missing_ids[0]} | Actor:{actor_id}')
                raise NotfoundError('Account not found.')
            ordered_rows = [rows_by_id[account_id] for account_id in params.ids]
            items = [cls._to_base_response(row) for row in ordered_rows]
            now = datetime.now(UTC)
            for row in ordered_rows:
                row.status = AccountStatus.ARCHIVED
                row.deleted_at = now
                row.modified_at = now
                row.email = f'archived+{row.id}@deleted.local'
            await Account.bulk_update(
                ordered_rows,
                fields=['status', 'deleted_at', 'modified_at', 'email'],
                using_db=connection,
            )
            session_count_rows = (
                await AuthSession.filter(
                    account_id__in=params.ids,
                    deleted_at=None,
                    revoked_at=None,
                )
                .using_db(connection)
                .group_by('account_id')
                .annotate(revoked_count=Count('id'))
                .values('account_id', 'revoked_count')
            )
            revoked_session_counts = {str(row['account_id']): int(row['revoked_count']) for row in session_count_rows}
            await (
                AuthSession.filter(
                    account_id__in=params.ids,
                    deleted_at=None,
                    revoked_at=None,
                )
                .using_db(connection)
                .update(revoked_at=now)
            )
            auth_rows = await Auth.filter(account_id__in=params.ids, deleted_at=None).using_db(connection)
            for auth in auth_rows:
                auth.deleted_at = now
                auth.modified_at = now
                auth.identifier = f'archived+{auth.id}'
            if auth_rows:
                await Auth.bulk_update(auth_rows, fields=['deleted_at', 'modified_at', 'identifier'], using_db=connection)
        for row in ordered_rows:
            revoked_session_count = revoked_session_counts.get(row.id, 0)
            log.info(f'Account {row.id} archived | Actor:{actor_id} | RevokedSessions:{revoked_session_count}')
        return AccountArchiveResult(total=len(items), items=items)

    @classmethod
    async def archive_account(cls, account_id: str, actor_id: str | None = None) -> AccountBase:
        """Archive one user-role account.

        Raises:
            NotfoundError: account does not exist.

        Side effects:
            Releases unique identity fields and revokes sessions.
        """
        result = await cls.archive_accounts(ArchiveAccountsParams(ids=[account_id]), actor_id=actor_id)
        return result.items[0]

    @staticmethod
    async def _get_account(account_id: str, include_archived: bool = False) -> Account:
        if include_archived:
            query = Account.filter(role=AccountRole.USER)
        else:
            query = Account.filter(role=AccountRole.USER, deleted_at=None).exclude(status=AccountStatus.ARCHIVED)
        account = await query.filter(id=account_id).first()
        if not account:
            raise NotfoundError('Account not found.')
        return account

    @staticmethod
    async def _revoke_account_sessions(
        account_id: str,
        *,
        revoked_at: datetime,
        using_db: BaseDBAsyncClient,
    ) -> int:
        return await (
            AuthSession.filter(account_id=account_id, deleted_at=None, revoked_at=None)
            .using_db(using_db)
            .update(revoked_at=revoked_at)
        )

    @staticmethod
    def _to_base_response(account: Account) -> AccountBase:
        return AccountBase(**account.model_dump())

    @staticmethod
    def _to_detail_response(account: Account, gateway_count: int, app_count: int) -> AccountDetail:
        return AccountDetail(**account.model_dump(), gateway_count=gateway_count, app_count=app_count)
