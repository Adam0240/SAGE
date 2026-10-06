# Tests password hashing, verification, and replacing login credentials.

import unittest
from services.password_service import PasswordService
from unittest.mock import Mock
from database.models import User
from database.user_repository import UserRepository
from services.account_service import AccountService
from services.authentication_service import AuthenticationService


class TestPasswordService(unittest.TestCase):
    def setUp(self):
        self.service = PasswordService()

    # Tests that hashing hides the password, accepts its original value, and rejects a wrong value.
    def test_hash_and_verify_password(self):
        password = "Example password for testing"
        password_hash = self.service.hash_password(password)

        self.assertNotEqual(password_hash, password)
        self.assertTrue(
            self.service.verify_password(password_hash, password)
        )

        self.assertFalse(
            self.service.verify_password(
                password_hash,
                "Incorrect test password",
            )
        )

    # Tests that an invalid stored hash fails verification without crashing.
    def test_invalid_hash_is_rejected(self):
        self.assertFalse(
            self.service.verify_password(
                "not-a-valid-hash",
                "Example test password",
            )
        )


    # Tests that random salts produce different hashes for the same
    # password and that both hashes still verify correctly.
    def test_same_password_produces_different_hashes(self):
        password = "Shared test password"
        first_hash = self.service.hash_password(password)
        second_hash = self.service.hash_password(password)

        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(
            self.service.verify_password(first_hash, password)
        )
        self.assertTrue(
            self.service.verify_password(second_hash, password)
        )


class TestPasswordChange(unittest.TestCase):
    # Tests that a specialist's own password change accepts the new password and rejects the old one.
    def test_password_change_replaces_login_credentials(self):
        passwords = PasswordService()
        old_password, new_password = "Original long password", "Replacement long password"
        user = User(id=1, name="Specialist", username="specialist", role="steam_specialist",
                    password_hash=passwords.hash_password(old_password), is_active=True)
        repository = Mock(spec=UserRepository)
        repository.get_by_id.return_value = user
        repository.lock_accounts.return_value = {1: user}
        repository.get_by_username.return_value = user
        repository.update.side_effect = lambda account: account
        authentication = AuthenticationService(repository, passwords)
        self.assertIs(authentication.authenticate("specialist", old_password), user)
        original_hash = user.password_hash

        AccountService(repository, passwords).update_account(1, 1, password=new_password)

        self.assertNotEqual(user.password_hash, original_hash)
        self.assertNotEqual(user.password_hash, new_password)
        self.assertIsNone(authentication.authenticate("specialist", old_password))
        self.assertIs(authentication.authenticate("specialist", new_password), user)
        self.assertEqual((user.name, user.username, user.role),
                         ("Specialist", "specialist", "steam_specialist"))
        repository.update.assert_called_once_with(user)
