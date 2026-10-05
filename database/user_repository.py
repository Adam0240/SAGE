# Handles database operations for SAGE user accounts.

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User


class UserRepository:
    def __init__(self, session: Session):
        # Use the database session supplied by the service.
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        # Return the matching user, or None if the ID does not exist.
        return self.session.get(User, user_id)

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