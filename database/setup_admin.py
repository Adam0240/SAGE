# Creates the first Boss Admin account in an empty SAGE users table.
# Later accounts must be created through authenticated account management.

from getpass import getpass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database.connection import DatabaseConfigurationError, SessionLocal
from database.models import User
from database.user_repository import UserRepository
from services.identity_validation import (
    validate_password,
    validated_name,
    validated_username,
)
from services.password_service import PasswordService


def main():
    # Check whether initial setup is still available before asking for details.
    try:
        with SessionLocal() as session:
            repository = UserRepository(session)

            if repository.get_all():
                print("Setup cancelled: SAGE accounts already exist.")
                return
    except DatabaseConfigurationError as error:
        print(error)
        return
    except SQLAlchemyError:
        print(
            "Could not read the users table. "
            "Check that Docker is running and the migration is applied."
        )
        return

    print("Create the first SAGE Boss Admin account.")

    name = input("Full name: ")
    username = input("Username: ")

    # Validate values against the database field lengths.
    try:
        name = validated_name(name)
        username = validated_username(username,
            length_message="Username must contain between 1 and 50 characters.",
            spaces_message="Username cannot contain spaces.")
    except ValueError as error:
        print(error)
        return

    # Password input is hidden and is never printed or written to a log.
    password = getpass("Password (at least 12 characters): ")
    confirmation = getpass("Confirm password: ")

    try:
        validate_password(password)
    except ValueError as error:
        print(error)
        return

    if password != confirmation:
        print("Passwords do not match. Run the script again.")
        return

    password_service = PasswordService()
    password_hash = password_service.hash_password(password)

    try:
        # Commit on success or roll back automatically if an error occurs.
        with SessionLocal.begin() as session:
            # Prevent two setup processes from creating initial accounts
            # at the same time.
            session.execute(
                text("LOCK TABLE users IN EXCLUSIVE MODE")
            )

            repository = UserRepository(session)

            # Check again inside the locked transaction before inserting.
            if repository.get_all():
                print("Setup cancelled: SAGE accounts already exist.")
                return

            user = User(
                name=name,
                username=username,
                password_hash=password_hash,
                role="boss_admin",
                is_active=True,
            )

            repository.add(user)

        print(f"Boss Admin account '{username}' created successfully.")

    except SQLAlchemyError:
        # Avoid printing database error details that could include account data.
        print("Account creation failed. No account was saved.")


if __name__ == "__main__":
    main()
