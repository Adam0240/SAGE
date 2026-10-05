# Tests password handling without connecting to the database.

import unittest

from services.password_service import PasswordService


class TestPasswordService(unittest.TestCase):
    def setUp(self):
        self.service = PasswordService()

    # Tests that hashing produces a different value and accepts the
    # original password during verification.
    def test_correct_password_is_accepted(self):
        password = "Example password for testing"
        password_hash = self.service.hash_password(password)

        self.assertNotEqual(password_hash, password)
        self.assertTrue(
            self.service.verify_password(password_hash, password)
        )

    # Tests that an incorrect password is rejected.
    def test_incorrect_password_is_rejected(self):
        password_hash = self.service.hash_password("Correct test password")

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

    # Tests that an empty password cannot be used to create a hash.
    def test_empty_password_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.hash_password("")

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

    # Tests that a new hash already uses the current hashing settings.
    def test_new_hash_does_not_need_rehashing(self):
        password_hash = self.service.hash_password("Example test password")

        self.assertFalse(self.service.needs_rehash(password_hash))


if __name__ == "__main__":
    unittest.main()