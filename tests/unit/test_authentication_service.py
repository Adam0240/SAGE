# Tests administrator login decisions without connecting to PostgreSQL.

import unittest
from unittest.mock import Mock

from database.models import User
from database.user_repository import UserRepository
from services.authentication_service import AuthenticationService
from services.password_service import PasswordService


class TestAuthenticationService(unittest.TestCase):
    def setUp(self):
        self.password_service = PasswordService()
        self.repository = Mock(spec=UserRepository)
        self.service = AuthenticationService(
            self.repository,
            self.password_service,
        )

        self.user = User(
            id=1,
            name="Test Boss",
            username="boss",
            password_hash=self.password_service.hash_password(
                "Correct test password"
            ),
            role="boss_admin",
            is_active=True,
        )
        self.repository.get_by_username.return_value = self.user


    # Tests that all three active staff roles can authenticate with their correct password.
    def test_correct_credentials_for_all_roles(self):
        for role in ("boss_admin", "steam_specialist", "base_specialist"):
            with self.subTest(role=role):
                self.user.role = role
                self.assertIs(self.service.authenticate("boss", "Correct test password"), self.user)

    # Tests rejection of wrong passwords, missing/inactive users, and blank credentials.
    def test_invalid_login_is_rejected(self):
        self.assertIsNone(self.service.authenticate("boss", "Wrong test password"))
        self.repository.get_by_username.return_value = None
        self.assertIsNone(self.service.authenticate("unknown", "Correct test password"))
        self.repository.get_by_username.return_value = self.user
        self.user.is_active = False
        self.assertIsNone(self.service.authenticate("boss", "Correct test password"))
        self.repository.reset_mock()
        self.assertIsNone(self.service.authenticate(" ", "password"))
        self.assertIsNone(self.service.authenticate("boss", ""))
        self.repository.get_by_username.assert_not_called()

    # Tests that username case and surrounding spaces are normalized.
    def test_username_is_normalized(self):
        result = self.service.authenticate(
            "  BOSS  ",
            "Correct test password",
        )

        self.assertIs(result, self.user)
        self.repository.get_by_username.assert_called_once_with("boss")



if __name__ == "__main__":
    unittest.main()
