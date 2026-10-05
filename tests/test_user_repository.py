# Tests database operations using a separate PostgreSQL test database.
# Each test's changes are rolled back so test accounts are not retained.

import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import Base, database_url
from database.models import User
from database.user_repository import UserRepository


class TestUserRepository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use the same server and credentials, but a separate database.
        test_url = database_url.set(database="sage_test")

        # Prevent accidentally running these tests against the SAGE database.
        if database_url.database == test_url.database:
            raise RuntimeError(
                "The application and test databases must be different."
            )

        cls.engine = create_engine(test_url)
        cls.addClassCleanup(cls.engine.dispose)

        # Create model tables in the test database only.
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        # Give each test its own connection and transaction.
        self.connection = self.engine.connect()
        self.addCleanup(self.connection.close)

        self.transaction = self.connection.begin()
        self.addCleanup(self.transaction.rollback)

        # A savepoint allows session rollback without ending the outer
        # transaction that keeps each test isolated.
        self.session = Session(
            bind=self.connection,
            join_transaction_mode="create_savepoint",
        )
        self.addCleanup(self.session.close)

        self.repository = UserRepository(self.session)

    def make_user(self, username="test_specialist"):
        # Build a test account. This placeholder is not a real password hash;
        # these tests cover storage, not authentication.
        return User(
            name="Test Specialist",
            username=username,
            password_hash="test-only-placeholder",
            role="base_specialist",
            is_active=True,
        )

    # Tests that an account can be added and retrieved by its generated ID.
    def test_add_and_get_user_by_id(self):
        user = self.repository.add(self.make_user())
        user_id = user.id

        self.assertIsNotNone(user_id)

        # Remove cached objects so retrieval must read from the database.
        self.session.expunge_all()

        saved_user = self.repository.get_by_id(user_id)

        self.assertIsNotNone(saved_user)
        self.assertEqual(saved_user.name, "Test Specialist")
        self.assertEqual(saved_user.username, "test_specialist")
        self.assertEqual(saved_user.role, "base_specialist")
        self.assertTrue(saved_user.is_active)

    # Tests that an account can be retrieved using its unique username.
    def test_get_user_by_username(self):
        user = self.repository.add(self.make_user())
        user_id = user.id
        self.session.expunge_all()

        saved_user = self.repository.get_by_username("test_specialist")

        self.assertIsNotNone(saved_user)
        self.assertEqual(saved_user.id, user_id)

    # Tests that a missing ID and username both return None.
    def test_missing_user_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(-1))
        self.assertIsNone(
            self.repository.get_by_username("missing_test_account")
        )

    # Tests that the account list includes added users in username order.
    def test_get_all_users_in_username_order(self):
        self.repository.add(self.make_user("test_zebra"))
        self.repository.add(self.make_user("test_alpha"))
        self.session.expunge_all()

        users = self.repository.get_all()
        usernames = [user.username for user in users]

        self.assertIn("test_alpha", usernames)
        self.assertIn("test_zebra", usernames)
        self.assertLess(
            usernames.index("test_alpha"),
            usernames.index("test_zebra"),
        )

    # Tests that changes to an existing account are saved in the database.
    def test_update_user(self):
        user = self.repository.add(self.make_user())
        user_id = user.id

        user.name = "Updated Specialist"
        user.username = "updated_specialist"
        user.password_hash = "updated-test-only-placeholder"

        self.repository.update(user)
        self.session.expunge_all()

        updated_user = self.repository.get_by_id(user_id)

        self.assertIsNotNone(updated_user)
        self.assertEqual(updated_user.name, "Updated Specialist")
        self.assertEqual(updated_user.username, "updated_specialist")
        self.assertEqual(
            updated_user.password_hash,
            "updated-test-only-placeholder",
        )
        self.assertIsNone(
            self.repository.get_by_username("test_specialist")
        )

    # Tests that deleting an account removes it from database queries.
    def test_delete_user(self):
        user = self.repository.add(self.make_user())
        user_id = user.id

        self.repository.delete(user)
        self.session.expunge_all()

        self.assertIsNone(self.repository.get_by_id(user_id))
        self.assertIsNone(
            self.repository.get_by_username("test_specialist")
        )

    # Tests that the database rejects two accounts with the same username.
    def test_duplicate_username_is_rejected(self):
        self.repository.add(self.make_user("duplicate_test_user"))

        with self.assertRaises(IntegrityError):
            self.repository.add(self.make_user("duplicate_test_user"))

        # Restore the session after the expected database error.
        self.session.rollback()


if __name__ == "__main__":
    unittest.main()