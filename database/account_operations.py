# Runs account changes in database transactions.

from database.connection import SessionLocal
from database.user_repository import UserRepository
from services.account_service import AccountService
from services.password_service import PasswordService


def _make_service(session) -> AccountService:
    # Give the account service a repository using this transaction.
    return AccountService(
        UserRepository(session),
        PasswordService(),
    )

def list_accounts(
    actor_id: int,
) -> list[tuple[int, str, str, str, bool]]:
    # Read account details only after checking the current database role.
    with SessionLocal() as session:
        # Return display fields while the database session is still open.
        # Password hashes are never sent to the interface.
        return [
            (user.id, user.name, user.username, user.role, user.is_active)
            for user in _make_service(session).list_accounts(actor_id)
        ]

def create_account(
    actor_id: int,
    name: str,
    username: str,
    password: str,
    role: str,
) -> int:
    # Commit the new account only if validation and insertion succeed.
    with SessionLocal.begin() as session:
        user = _make_service(session).create_account(
            actor_id, name, username, password, role
        )
        return user.id


def update_account(
    actor_id: int,
    target_id: int,
    *,
    name: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    # An exception rolls back any changes to the account.
    with SessionLocal.begin() as session:
        _make_service(session).update_account(
            actor_id,
            target_id,
            name=name,
            username=username,
            password=password,
        )


def delete_account(actor_id: int, target_id: int) -> None:
    # Permission checks and deletion share one transaction.
    with SessionLocal.begin() as session:
        _make_service(session).delete_account(actor_id, target_id)


def change_role(
    actor_id: int,
    target_id: int,
    new_role: str,
) -> None:
    # Permission checks and the role change share one transaction.
    with SessionLocal.begin() as session:
        _make_service(session).change_role(
            actor_id, target_id, new_role
        )
