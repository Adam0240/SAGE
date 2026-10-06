# Handles database operations for SAGE user accounts.

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database.models import User


# PostgreSQL's two-integer advisory-lock namespace: "SAGE", active boss status.
# Every deletion, demotion, or future deactivation must use this same key.
BOSS_ADMIN_STATUS_LOCK = (0x53414745, 1)


class UserRepository:
    def __init__(self, session: Session):
        # Use the database session supplied by the service.
        self.session = session

    def lock_boss_admin_status(self) -> None:
        # Call before reading accounts in a dedicated account-change transaction.
        # PostgreSQL releases this lock automatically on commit or rollback.
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :resource)"),
            dict(zip(("namespace", "resource"), BOSS_ADMIN_STATUS_LOCK)),
        )
        # A session may have cached roles before waiting for another transaction.
        # Re-read those values after acquiring the lock, rather than trusting them.
        self.session.expire_all()

    def get_by_id(self, user_id: int) -> User | None:
        # Return the matching user, or None if the ID does not exist.
        return self.session.get(User, user_id)

    def lock_accounts(self, *user_ids: int) -> dict[int, User]:
        # All mutation paths lock distinct account IDs in ascending order.
        # If an advisory lock is needed, acquire it before any of these row locks.
        # The caller's transaction retains the row locks through commit/rollback.
        accounts = {}
        for user_id in sorted(set(user_ids)):
            statement = (
                select(User)
                .where(User.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            # Refresh cached roles/status after a competing writer releases its lock.
            user = self.session.scalar(statement)
            if user is not None:
                accounts[user_id] = user
        return accounts

    def get_by_username(self, username: str) -> User | None:
        # Find an account using its unique username.
        statement = select(User).where(User.username == username)
        return self.session.scalar(statement)

    def get_all(self) -> list[User]:
        # Return accounts in username order.
        statement = select(User).order_by(User.username)
        return list(self.session.scalars(statement))

    def add(self, user: User) -> User:
        # Insert a user whose password has already been hashed.
        self.session.add(user)
        self.session.flush()
        return user

    def update(self, user: User) -> User:
        # Save changes to a user retrieved through this session.
        self.session.add(user)
        self.session.flush()
        return user

    def delete(self, user: User) -> None:
        # Delete a user after the service has checked permissions.
        self.session.delete(user)
        self.session.flush()
