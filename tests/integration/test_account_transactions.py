# Tests real account-operation commits and rollbacks in a separate PostgreSQL test database.

import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database.connection import Base, database_url
from database.models import User
from database.user_repository import UserRepository
from database import account_operations


class TestAccountTransactions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_url = database_url.set(database="sage_test")
        if test_url.database == database_url.database:
            raise RuntimeError("The application and test databases must be different.")
        cls.engine = create_engine(test_url)
        cls.addClassCleanup(cls.engine.dispose)
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        self.connection = self.engine.connect()
        self.addCleanup(self.connection.close)
        self.transaction = self.connection.begin()
        self.addCleanup(self.transaction.rollback)
        # Each wrapper owns its real session/transaction within the outer test rollback.
        self.sessions = sessionmaker(bind=self.connection, join_transaction_mode="create_savepoint")
        self.session_patch = patch.object(account_operations, "SessionLocal", self.sessions)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.suffix = uuid4().hex[:12]
        with self.sessions.begin() as session:
            boss = User(name="Boss", username=f"boss_{self.suffix}", role="boss_admin",
                        password_hash="seed-hash", is_active=True)
            student = User(name="Student", username=f"student_{self.suffix}", role="base_specialist",
                           password_hash="seed-hash", is_active=True)
            session.add_all([boss, student])
            session.flush()
            self.boss_id, self.student_id = boss.id, student.id
            self.boss_username, self.student_username = boss.username, student.username

    # Tests that the creation wrapper commits a hashed account visible to a subsequent session.
    def test_create_commits_account(self):
        user_id = account_operations.create_account(
            self.boss_id, "New Student", f"new_{self.suffix}", "long-test-password", "base_specialist")
        with self.sessions() as session:
            user = session.get(User, user_id)
            self.assertIsNotNone(user)
            self.assertEqual((user.name, user.role), ("New Student", "base_specialist"))
            self.assertNotEqual(user.password_hash, "long-test-password")

    # Tests real username lookup and account reads, with specialists seeing only themselves and students.
    def test_read_accounts_and_lookup_username(self):
        specialist_id = account_operations.create_account(
            self.boss_id, "Specialist", f"specialist_{self.suffix}",
            "long-test-password", "steam_specialist")
        boss_accounts = account_operations.list_accounts(self.boss_id)
        self.assertTrue({self.boss_id, self.student_id, specialist_id}.issubset(
            {account[0] for account in boss_accounts}))
        specialist_accounts = account_operations.list_accounts(specialist_id)
        self.assertTrue({specialist_id, self.student_id}.issubset(
            {account[0] for account in specialist_accounts}))
        self.assertNotIn(self.boss_id, {account[0] for account in specialist_accounts})
        self.assertTrue(all(len(account) == 5 and (
            account[0] == specialist_id or account[3] == "base_specialist")
            for account in specialist_accounts))
        with self.sessions() as session:
            repository = UserRepository(session)
            self.assertEqual(repository.get_by_username(self.student_username).id, self.student_id)
            self.assertIsNone(repository.get_by_username(f"missing_{self.suffix}"))
            self.assertIsNone(repository.get_by_id(-1))

    # Tests that the update wrapper commits identity changes visible from a separate session.
    def test_update_commits_changes(self):
        account_operations.update_account(self.boss_id, self.student_id, name="Updated Student")
        with self.sessions() as session:
            self.assertEqual(session.get(User, self.student_id).name, "Updated Student")

    # Tests that the deletion wrapper commits removal rather than leaving an uncommitted row.
    def test_delete_commits_removal(self):
        account_operations.delete_account(self.boss_id, self.student_id)
        with self.sessions() as session:
            self.assertIsNone(session.get(User, self.student_id))

    # Tests that the role-change wrapper commits the new role for a subsequent session to read.
    def test_role_change_commits_changes(self):
        account_operations.change_role(self.boss_id, self.student_id, "steam_specialist")
        with self.sessions() as session:
            self.assertEqual(session.get(User, self.student_id).role, "steam_specialist")

    # Tests that a duplicate-username update rolls back name, username, and password and permits retry.
    def test_duplicate_update_rolls_back_all_fields(self):
        with self.assertRaises(IntegrityError):
            account_operations.update_account(self.boss_id, self.student_id, name="Must Roll Back",
                                              username=self.boss_username, password="long-test-password")
        with self.sessions() as session:
            user = session.get(User, self.student_id)
            self.assertEqual((user.name, user.username, user.password_hash),
                             ("Student", self.student_username, "seed-hash"))
        account_operations.update_account(self.boss_id, self.student_id, name="Retry Worked")
        with self.sessions() as session:
            self.assertEqual(session.get(User, self.student_id).name, "Retry Worked")

    # Tests that failed duplicate creation leaves existing rows intact and the next creation can commit.
    def test_duplicate_create_rolls_back_and_allows_retry(self):
        with self.assertRaises(IntegrityError):
            account_operations.create_account(self.boss_id, "Duplicate", self.student_username,
                                              "long-test-password", "base_specialist")
        with self.sessions() as session:
            self.assertEqual(session.get(User, self.student_id).name, "Student")
        user_id = account_operations.create_account(self.boss_id, "Retry", f"retry_{self.suffix}",
                                                     "long-test-password", "base_specialist")
        with self.sessions() as session:
            self.assertEqual(session.get(User, user_id).name, "Retry")
