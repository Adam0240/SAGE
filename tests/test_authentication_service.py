# Tests administrator login decisions without connecting to PostgreSQL.

import unittest
from unittest.mock import Mock

from database.models import User
from services.authentication_service import AuthenticationService
from services.password_service import PasswordService


class TestAuthenticationService(unittest.TestCase):
    def setUp(self):
        self.password_service = PasswordService()
        self.repository = Mock()
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

    # Tests that correct credentials return the active administrator.
    def test_correct_credentials(self):
        result = self.service.authenticate(
            "boss",
            "Correct test password",
        )

        self.assertIs(result, self.user)

    # Tests that a wrong password cannot authenticate an existing account.
    def test_wrong_password(self):
        result = self.service.authenticate(
            "boss",
            "Wrong test password",
        )

        self.assertIsNone(result)

    # Tests that a username not found in the repository cannot log in.
    def test_unknown_username(self):
        self.repository.get_by_username.return_value = None

        result = self.service.authenticate(
            "unknown",
            "Correct test password",
        )

        self.assertIsNone(result)

    # Tests that a disabled account cannot log in with a correct password.
    def test_inactive_account(self):
        self.user.is_active = False

        result = self.service.authenticate(
            "boss",
            "Correct test password",
        )

        self.assertIsNone(result)

    # Tests that username case and surrounding spaces are normalized.
    def test_username_is_normalized(self):
        result = self.service.authenticate(
            "  BOSS  ",
            "Correct test password",
        )

        self.assertIs(result, self.user)
        self.repository.get_by_username.assert_called_once_with("boss")

    # Tests that blank credentials are rejected without querying accounts.
    def test_blank_credentials(self):
        self.assertIsNone(self.service.authenticate(" ", "password"))
        self.assertIsNone(self.service.authenticate("boss", ""))

        self.repository.get_by_username.assert_not_called()


if __name__ == "__main__":
    unittest.main()