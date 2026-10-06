# Tests competing boss removals with real commits on independent PostgreSQL connections.

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from database import account_operations
from database.connection import Base, get_database_url
from database.models import User
from database.user_repository import UserRepository
from services.password_service import PasswordService


class TestBossAdminConcurrency(unittest.TestCase):
    def setUp(self):
        database_url = get_database_url()
        test_url = database_url.set(database="sage_test")
        if test_url.database == database_url.database:
            raise RuntimeError("The application and test databases must be different.")
        self.engine = create_engine(
            test_url,
            isolation_level="READ COMMITTED",
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
        )
        self.addCleanup(self.engine.dispose)
        # Isolate both the account rows and boss count from any existing test data.
        self.schema = f"boss_lock_test_{uuid4().hex}"
        with self.engine.begin() as connection:
            connection.execute(CreateSchema(self.schema))
        self.addCleanup(self.drop_schema)
        self.test_engine = self.engine.execution_options(
            schema_translate_map={None: self.schema}
        )
        Base.metadata.create_all(self.test_engine)
        self.sessions = sessionmaker(bind=self.test_engine)
        patcher = patch.object(account_operations, "SessionLocal", self.sessions)
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.sessions.begin() as session:
            bosses = [
                User(name=f"Boss {index}", username=f"boss{index}",
                     role="boss_admin", password_hash="seed-hash", is_active=True)
                for index in (1, 2)
            ]
            session.add_all(bosses)
            session.flush()
            self.first_id, self.second_id = [boss.id for boss in bosses]

    def drop_schema(self):
        # This generated schema belongs exclusively to this test; public is untouched.
        with self.engine.begin() as connection:
            connection.execute(DropSchema(self.schema, cascade=True))

    def run_overlapping_operations(
        self, first_operation, second_operation,
        lock_method="lock_boss_admin_status", second_error=PermissionError,
        expected_boss_count=1, pause_after_first_row=False,
    ):
        first_locked = threading.Event()
        second_connected = threading.Event()
        overlap_observed = threading.Event()
        connection_ids = {}
        cached_accounts = {}
        original_lock = getattr(UserRepository, lock_method)

        def wait_for_blocked_competitor(connection):
            first_locked.set()
            if not second_connected.wait(5):
                raise AssertionError("Second database connection did not start")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                # Query from the first connection to prove the second is waiting.
                blocked = connection.scalar(text(
                    "SELECT pg_backend_pid() = ANY(pg_blocking_pids(:pid))"
                ), {"pid": connection_ids["second"]})
                if blocked:
                    overlap_observed.set()
                    return
                time.sleep(0.01)
            raise AssertionError("Competing mutation never waited for the lock")

        def pause_first_row(connection, _cursor, statement, _parameters, _context, _many):
            if (threading.current_thread().name.endswith("_0")
                    and "FOR UPDATE" in statement and not first_locked.is_set()):
                # Force overlap before the first operation locks its second row.
                # Opposite input order would deadlock here without sorted IDs.
                wait_for_blocked_competitor(connection)

        def coordinated_lock(repository, *user_ids):
            pid = repository.session.scalar(text("SELECT pg_backend_pid()"))
            if threading.current_thread().name.endswith("_0"):
                connection_ids["first"] = pid
                result = original_lock(repository, *user_ids)
                if not pause_after_first_row:
                    wait_for_blocked_competitor(repository.session)
                return result
            connection_ids["second"] = pid
            # Retain pre-lock ORM instances so this also verifies stale cached
            # roles/rows are expired after waiting for the first commit.
            cached_accounts["second"] = repository.get_all()
            self.assertGreaterEqual(len(cached_accounts["second"]), 2)
            second_connected.set()
            return original_lock(repository, *user_ids)

        if pause_after_first_row:
            event.listen(self.test_engine, "after_cursor_execute", pause_first_row)
        try:
            with patch.object(UserRepository, lock_method, coordinated_lock):
                with ThreadPoolExecutor(max_workers=2, thread_name_prefix="account_mutation") as pool:
                    first = pool.submit(first_operation)
                    self.assertTrue(first_locked.wait(5), "First operation did not acquire its lock")
                    second = pool.submit(second_operation)
                    first.result(timeout=12)
                    if second_error is None:
                        second.result(timeout=12)
                    else:
                        with self.assertRaises(second_error):
                            second.result(timeout=12)
        finally:
            if pause_after_first_row:
                event.remove(self.test_engine, "after_cursor_execute", pause_first_row)

        self.assertTrue(overlap_observed.is_set())
        self.assertNotEqual(connection_ids["first"], connection_ids["second"])
        with self.sessions() as session:
            accounts = list(session.scalars(select(User).order_by(User.id)))
            self.assertEqual(sum(user.role == "boss_admin" and user.is_active
                                 for user in accounts), expected_boss_count)
            return [(user.id, user.role) for user in accounts]

    # Tests that two self-demotions overlap and the second cannot remove the final boss.
    def test_concurrent_self_demotions_preserve_one_boss(self):
        accounts = self.run_overlapping_operations(
            lambda: account_operations.change_role(self.first_id, self.first_id, "steam_specialist"),
            lambda: account_operations.change_role(self.second_id, self.second_id, "steam_specialist"),
        )
        self.assertEqual(accounts, [(self.first_id, "steam_specialist"),
                                    (self.second_id, "boss_admin")])

    # Tests that competing self-deletions cannot both commit and the rejected row remains.
    def test_concurrent_self_deletions_preserve_one_boss(self):
        accounts = self.run_overlapping_operations(
            lambda: account_operations.delete_account(self.first_id, self.first_id),
            lambda: account_operations.delete_account(self.second_id, self.second_id),
        )
        self.assertEqual(accounts, [(self.second_id, "boss_admin")])

    # Tests that deletion and demotion share one lock rather than separate operation locks.
    def test_demotion_competing_with_deletion_preserves_one_boss(self):
        accounts = self.run_overlapping_operations(
            lambda: account_operations.change_role(self.first_id, self.first_id, "steam_specialist"),
            lambda: account_operations.delete_account(self.second_id, self.second_id),
        )
        self.assertEqual(accounts, [(self.first_id, "steam_specialist"),
                                    (self.second_id, "boss_admin")])

    # Tests that an actor deleted by a competing operation is re-read and denied permission.
    def test_concurrent_cross_deletions_recheck_actor(self):
        accounts = self.run_overlapping_operations(
            lambda: account_operations.delete_account(self.first_id, self.second_id),
            lambda: account_operations.delete_account(self.second_id, self.first_id),
        )
        self.assertEqual(accounts, [(self.first_id, "boss_admin")])

    def add_specialist_and_assistant(self):
        self.original_password_hash = PasswordService().hash_password("original long password")
        with self.sessions.begin() as session:
            specialist = User(name="Specialist", username="specialist", role="steam_specialist",
                              password_hash=self.original_password_hash, is_active=True)
            assistant = User(name="Assistant", username="assistant", role="base_specialist",
                             password_hash=self.original_password_hash, is_active=True)
            session.add_all([specialist, assistant])
            session.flush()
            self.specialist_id, self.assistant_id = specialist.id, assistant.id

    # Tests a reset waits for promotion, refreshes cached roles, and cannot reset a new boss.
    def test_promotion_blocks_and_rejects_specialist_password_reset(self):
        self.add_specialist_and_assistant()
        self.run_overlapping_operations(
            lambda: account_operations.change_role(self.first_id, self.assistant_id, "boss_admin"),
            lambda: account_operations.update_account(
                self.specialist_id, self.assistant_id, password="replacement long password"),
            lock_method="lock_accounts", expected_boss_count=3,
        )
        with self.sessions() as session:
            assistant = session.get(User, self.assistant_id)
            self.assertEqual(assistant.role, "boss_admin")
            self.assertEqual(assistant.password_hash, self.original_password_hash)

    # Tests a reset authorized first commits before promotion can change its locked target.
    def test_password_reset_blocks_promotion_until_commit(self):
        self.add_specialist_and_assistant()
        self.run_overlapping_operations(
            lambda: account_operations.update_account(
                self.specialist_id, self.assistant_id, password="replacement long password"),
            lambda: account_operations.change_role(self.first_id, self.assistant_id, "boss_admin"),
            lock_method="lock_accounts", second_error=None, expected_boss_count=3,
        )
        with self.sessions() as session:
            assistant = session.get(User, self.assistant_id)
            self.assertEqual(assistant.role, "boss_admin")
            self.assertTrue(PasswordService().verify_password(
                assistant.password_hash, "replacement long password"))

    # Tests creation rechecks its locked actor when a competing transaction revokes its role.
    def test_actor_demotion_blocks_and_rejects_account_creation(self):
        self.add_specialist_and_assistant()
        self.run_overlapping_operations(
            lambda: account_operations.change_role(self.first_id, self.specialist_id, "base_specialist"),
            lambda: account_operations.create_account(
                self.specialist_id, "New", "new", "long-test-password", "base_specialist"),
            lock_method="lock_accounts", expected_boss_count=2,
        )
        with self.sessions() as session:
            self.assertIsNone(UserRepository(session).get_by_username("new"))
            self.assertEqual(session.get(User, self.specialist_id).role, "base_specialist")

    # Tests password updates recheck a demoted actor rather than using its cached permission.
    def test_actor_demotion_blocks_and_rejects_password_reset(self):
        self.add_specialist_and_assistant()
        self.run_overlapping_operations(
            lambda: account_operations.change_role(self.first_id, self.specialist_id, "base_specialist"),
            lambda: account_operations.update_account(
                self.specialist_id, self.assistant_id, password="replacement long password"),
            lock_method="lock_accounts", expected_boss_count=2,
        )
        with self.sessions() as session:
            self.assertEqual(session.get(User, self.assistant_id).password_hash,
                             self.original_password_hash)

    # Tests reversed actor/target pairs overlap between row acquisitions without deadlocking.
    def test_opposing_updates_lock_rows_in_consistent_order(self):
        self.run_overlapping_operations(
            lambda: account_operations.update_account(self.second_id, self.first_id, name="First updated"),
            lambda: account_operations.update_account(self.first_id, self.second_id, name="Second updated"),
            lock_method="lock_accounts", second_error=None, expected_boss_count=2,
            pause_after_first_row=True,
        )
        with self.sessions() as session:
            self.assertEqual(session.get(User, self.first_id).name, "First updated")
            self.assertEqual(session.get(User, self.second_id).name, "Second updated")

    # Tests rollback releases the lock while its original database connection stays open.
    def test_rollback_releases_lock_and_allows_retry(self):
        with self.test_engine.connect() as first, self.test_engine.connect() as second:
            with self.assertRaisesRegex(ValueError, "Account not found"):
                with self.sessions(bind=first) as session, session.begin():
                    account_operations._make_service(session).delete_account(self.first_id, -1)
            with self.sessions(bind=second) as session, session.begin():
                session.execute(text("SET LOCAL lock_timeout = '1s'"))
                account_operations._make_service(session).change_role(
                    self.first_id, self.second_id, "steam_specialist"
                )
            # Both rows survived the failed deletion and the subsequent change committed.
            with self.sessions(bind=first) as session:
                self.assertEqual(session.get(User, self.first_id).role, "boss_admin")
                self.assertEqual(session.get(User, self.second_id).role, "steam_specialist")
