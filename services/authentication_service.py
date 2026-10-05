# Checks SAGE administrator credentials.

from database.models import User
from database.user_repository import UserRepository
from services.password_service import PasswordService


class AuthenticationService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_service: PasswordService,
    ):
        self.user_repository = user_repository
        self.password_service = password_service

    def authenticate(self, username: str, password: str) -> User | None:
        # Usernames are stored in lowercase by initial account setup.
        username = username.strip().lower()

        if not username or not password:
            return None

        user = self.user_repository.get_by_username(username)

        # Missing and disabled accounts cannot log in.
        if user is None or not user.is_active:
            return None

        # Return the account only when its password matches the stored hash.
        if not self.password_service.verify_password(
            user.password_hash,
            password,
        ):
            return None

        return user