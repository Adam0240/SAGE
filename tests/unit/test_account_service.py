# Tests account permissions, input validation, and safe display fields without a database.

import unittest
from unittest.mock import Mock, call, patch
from database.models import User
from database.user_repository import UserRepository
from services.account_service import AccountService
from services.password_service import PasswordService
from database.account_operations import list_accounts


ROLES = ("boss_admin", "steam_specialist", "base_specialist")


class TestAccountPermissions(unittest.TestCase):
    def setUp(self):
        self.reset_accounts()

    def reset_accounts(self):
        # Fresh accounts and mocks keep independent permission cases from affecting each other.
        self.users = {
            i: User(id=i, name=f"User {i}", username=f"user{i}", role=role,
                    password_hash="old-hash", is_active=True)
            for i, role in enumerate(ROLES + ROLES, start=1)
        }
        self.repository = Mock(spec=UserRepository)
        self.repository.get_by_id.side_effect = self.users.get
        self.repository.lock_accounts.side_effect = lambda *ids: {
            user_id: self.users[user_id] for user_id in ids if user_id in self.users
        }
        self.repository.get_all.side_effect = lambda: list(self.users.values())
        self.repository.add.side_effect = lambda user: user
        self.repository.update.side_effect = lambda user: user
        self.passwords = Mock(spec=PasswordService)
        self.passwords.hash_password.return_value = "new-hash"
        self.service = AccountService(self.repository, self.passwords)

    # Tests that bosses create any role, specialists create only students, and students create none.
    def test_create_permissions_by_role(self):
        for actor_id, actor_role in enumerate(ROLES, start=1):
            for new_role in ROLES:
                with self.subTest(actor=actor_role, new_role=new_role):
                    self.reset_accounts()
                    allowed = actor_role == "boss_admin" or (
                        actor_role == "steam_specialist" and new_role == "base_specialist")
                    if allowed:
                        user = self.service.create_account(actor_id, "  New User  ", "  NEW_USER  ",
                                                           "long-test-password", new_role)
                        self.assertEqual((user.name, user.username, user.role, user.password_hash),
                                         ("New User", "new_user", new_role, "new-hash"))
                        self.repository.add.assert_called_once_with(user)
                    else:
                        with self.assertRaises(PermissionError):
                            self.service.create_account(actor_id, "New User", "new_user",
                                                        "long-test-password", new_role)
                        self.repository.add.assert_not_called()

    # Tests that bosses read all users, specialists read self/students, and students cannot list users.
    def test_read_permissions_by_role(self):
        self.users[6].is_active = False
        self.assertEqual(self.service.list_accounts(1), list(self.users.values()))
        self.assertEqual(self.service.list_accounts(2), [self.users[i] for i in (2, 3, 6)])
        with self.assertRaises(PermissionError):
            self.service.list_accounts(3)

    # Tests update access for every actor/target role, including own passwords and normalized identity.
    def test_update_permissions_by_role(self):
        for actor_id in (1, 2, 3):
            for target_id in range(1, 7):
                with self.subTest(actor=actor_id, target=target_id):
                    self.reset_accounts()
                    actor, target = self.users[actor_id], self.users[target_id]
                    allowed = actor.role == "boss_admin" or (
                        actor.role == "steam_specialist" and
                        (target_id == actor_id or target.role == "base_specialist")) or (
                        actor.role == "base_specialist" and target_id == actor_id)
                    values = {"password": "long-test-password"}
                    if not (actor.role == "steam_specialist" and actor_id == target_id):
                        values.update(name="  Changed User  ", username="  CHANGED_USER  ")
                    if allowed:
                        self.service.update_account(actor_id, target_id, **values)
                        self.assertEqual(target.password_hash, "new-hash")
                        if "name" in values:
                            self.assertEqual((target.name, target.username), ("Changed User", "changed_user"))
                        else:
                            self.assertEqual((target.name, target.username), ("User 2", "user2"))
                        self.repository.update.assert_called_once_with(target)
                    else:
                        with self.assertRaises(PermissionError):
                            self.service.update_account(actor_id, target_id, **values)
                        self.assertEqual(target.password_hash, "old-hash")
                        self.repository.update.assert_not_called()
                        self.passwords.hash_password.assert_not_called()

    # Tests that bosses delete any account, specialists delete only students, and students delete none.
    def test_delete_permissions_by_role(self):
        for actor_id in (1, 2, 3):
            for target_id in range(1, 7):
                with self.subTest(actor=actor_id, target=target_id):
                    self.reset_accounts()
                    actor, target = self.users[actor_id], self.users[target_id]
                    allowed = actor.role == "boss_admin" or (
                        actor.role == "steam_specialist" and target.role == "base_specialist")
                    if allowed:
                        self.service.delete_account(actor_id, target_id)
                        self.repository.delete.assert_called_once_with(target)
                    else:
                        with self.assertRaises(PermissionError):
                            self.service.delete_account(actor_id, target_id)
                        self.repository.delete.assert_not_called()

    # Tests that only bosses may promote students or demote another boss when an active boss remains.
    def test_role_change_permissions(self):
        for actor_id in (1, 2, 3):
            with self.subTest(actor=actor_id):
                self.reset_accounts()
                if actor_id == 1:
                    self.service.change_role(1, 6, "boss_admin")
                    self.assertEqual(self.users[6].role, "boss_admin")
                    self.service.change_role(1, 4, "base_specialist")
                    self.assertEqual(self.users[4].role, "base_specialist")
                else:
                    with self.assertRaises(PermissionError):
                        self.service.change_role(actor_id, 6, "boss_admin")
                    self.repository.update.assert_not_called()

    # Tests that specialists cannot edit their own name/username even when also changing a password.
    def test_specialist_own_identity_is_protected(self):
        for field in ("name", "username"):
            with self.subTest(field=field):
                self.reset_accounts()
                with self.assertRaises(PermissionError):
                    self.service.update_account(2, 2, password="long-test-password", **{field: "changed"})
                self.assertEqual(self.users[2].password_hash, "old-hash")
                self.repository.update.assert_not_called()

    # Tests that missing/inactive actors cannot create, read, update, delete, or change roles.
    def test_missing_or_inactive_actor_is_rejected(self):
        operations = (
            lambda actor: self.service.create_account(actor, "New", "new", "long-test-password", "base_specialist"),
            lambda actor: self.service.list_accounts(actor),
            lambda actor: self.service.update_account(actor, 3, name="Changed"),
            lambda actor: self.service.delete_account(actor, 3),
            lambda actor: self.service.change_role(actor, 3, "steam_specialist"),
        )
        for operation in operations:
            for actor_id in (1, 99):
                with self.subTest(operation=operations.index(operation), actor=actor_id):
                    self.reset_accounts()
                    self.users[1].is_active = False
                    with self.assertRaises(PermissionError):
                        operation(actor_id)
                    self.repository.add.assert_not_called()
                    self.repository.update.assert_not_called()
                    self.repository.delete.assert_not_called()

    # Tests that updating, deleting, or changing roles of missing accounts fails without writes.
    def test_missing_target_is_rejected(self):
        operations = (
            lambda: self.service.update_account(1, 99, name="Changed"),
            lambda: self.service.delete_account(1, 99),
            lambda: self.service.change_role(1, 99, "steam_specialist"),
        )
        for index, operation in enumerate(operations):
            with self.subTest(operation=index), self.assertRaises(ValueError):
                operation()
        self.repository.update.assert_not_called()
        self.repository.delete.assert_not_called()

    # Tests that deletion/demotion of the last active boss fails even if an inactive boss exists.
    def test_last_active_boss_is_protected(self):
        for second_boss_exists in (False, True):
            for action in ("delete", "demote"):
                with self.subTest(second_boss=second_boss_exists, action=action):
                    self.reset_accounts()
                    if second_boss_exists:
                        self.users[4].is_active = False
                    else:
                        del self.users[4]
                    with self.assertRaises(PermissionError):
                        if action == "delete":
                            self.service.delete_account(1, 1)
                        else:
                            self.service.change_role(1, 1, "steam_specialist")
                    self.assertEqual(self.users[1].role, "boss_admin")
                    self.repository.delete.assert_not_called()
                    self.repository.update.assert_not_called()

    # Tests that removal operations lock before reading roles, counting, or writing.
    def test_boss_status_lock_precedes_account_reads(self):
        for action in ("delete", "demote"):
            with self.subTest(action=action):
                self.reset_accounts()
                if action == "delete":
                    self.service.delete_account(1, 4)
                else:
                    self.service.change_role(1, 4, "steam_specialist")
                self.assertEqual(self.repository.mock_calls[:2], [
                    call.lock_boss_admin_status(), call.lock_accounts(1, 4),
                ])
                self.repository.lock_boss_admin_status.assert_called_once_with()

    # Tests that inability to acquire the common lock prevents all account access/writes.
    def test_boss_status_lock_failure_stops_operation(self):
        for action in ("delete", "demote"):
            with self.subTest(action=action):
                self.reset_accounts()
                self.repository.lock_boss_admin_status.side_effect = RuntimeError("lock failed")
                with self.assertRaisesRegex(RuntimeError, "lock failed"):
                    if action == "delete":
                        self.service.delete_account(1, 4)
                    else:
                        self.service.change_role(1, 4, "steam_specialist")
                self.repository.get_by_id.assert_not_called()
                self.repository.lock_accounts.assert_not_called()
                self.repository.get_all.assert_not_called()
                self.repository.delete.assert_not_called()
                self.repository.update.assert_not_called()

    # Tests that failed row locking prevents authorization, hashing, and all writes.
    def test_row_lock_failure_stops_all_mutations(self):
        operations = (
            lambda: self.service.create_account(1, "New", "new", "long-test-password", "boss_admin"),
            lambda: self.service.update_account(1, 4, password="long-test-password"),
            lambda: self.service.delete_account(1, 4),
            lambda: self.service.change_role(1, 4, "steam_specialist"),
        )
        for index, operation in enumerate(operations):
            with self.subTest(operation=index):
                self.reset_accounts()
                self.repository.lock_accounts.side_effect = RuntimeError("row lock failed")
                with self.assertRaisesRegex(RuntimeError, "row lock failed"):
                    operation()
                self.repository.get_by_id.assert_not_called()
                self.repository.get_all.assert_not_called()
                self.passwords.hash_password.assert_not_called()
                self.repository.add.assert_not_called()
                self.repository.update.assert_not_called()
                self.repository.delete.assert_not_called()

    # Tests that a student promoted after listing cannot be updated or deleted through a stale entry.
    def test_current_target_role_is_checked(self):
        self.service.list_accounts(2)
        self.users[3].role = "steam_specialist"
        with self.assertRaises(PermissionError):
            self.service.update_account(2, 3, name="Changed")
        with self.assertRaises(PermissionError):
            self.service.delete_account(2, 3)
        self.repository.update.assert_not_called()
        self.repository.delete.assert_not_called()


class TestAccountValidation(unittest.TestCase):
    def setUp(self):
        self.actor = User(id=1, name="Boss", username="boss", role="boss_admin",
                          password_hash="original-hash", is_active=True)
        self.target = User(id=2, name="Student", username="student", role="base_specialist",
                           password_hash="original-hash", is_active=True)
        self.repository = Mock(spec=UserRepository)
        self.repository.get_by_id.side_effect = {1: self.actor, 2: self.target}.get
        self.repository.lock_accounts.side_effect = lambda *ids: {
            user_id: {1: self.actor, 2: self.target}[user_id]
            for user_id in ids if user_id in (1, 2)
        }
        self.repository.add.side_effect = lambda user: user
        self.repository.update.side_effect = lambda user: user
        self.passwords = Mock(spec=PasswordService)
        self.passwords.hash_password.return_value = "new-hash"
        self.service = AccountService(self.repository, self.passwords)

    # Tests that blank/oversized names, invalid usernames, and short passwords prevent creation.
    def test_invalid_creation_inputs_are_rejected(self):
        cases = (
            {"name": ""}, {"name": "   "}, {"name": "n" * 101},
            {"username": ""}, {"username": "   "}, {"username": "u" * 51},
            {"username": "two words"}, {"username": "two\twords"},
            {"password": ""}, {"password": "p" * 11}, {"role": "unknown"},
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                values = dict(name="Student", username="student", password="p" * 12,
                              role="base_specialist")
                values.update(invalid)
                with self.assertRaises(ValueError):
                    self.service.create_account(1, **values)
        self.repository.add.assert_not_called()
        self.passwords.hash_password.assert_not_called()

    # Tests that creation and updates accept maximum identity lengths and exactly 12 password characters.
    def test_create_and_update_accept_length_boundaries(self):
        user = self.service.create_account(1, "n" * 100, "u" * 50, "p" * 12, "base_specialist")
        self.assertEqual(user.name, "n" * 100)
        self.assertEqual(user.username, "u" * 50)
        self.assertEqual(user.password_hash, "new-hash")
        self.passwords.hash_password.assert_called_once_with("p" * 12)
        self.repository.add.assert_called_once_with(user)
        self.service.update_account(1, 2, name="n" * 100, username="u" * 50, password="p" * 12)
        self.assertEqual((self.target.name, self.target.username, self.target.password_hash),
                         ("n" * 100, "u" * 50, "new-hash"))
        self.repository.update.assert_called_once_with(self.target)

    # Tests that invalid updates neither mutate identity/password fields nor write to storage.
    def test_invalid_updates_leave_account_unchanged(self):
        cases = (
            {"name": ""}, {"name": "   "}, {"name": "n" * 101},
            {"username": ""}, {"username": "   "}, {"username": "u" * 51},
            {"username": "two words"}, {"username": "two\nwords"},
            {"password": ""}, {"password": "p" * 11},
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                values = dict(name="New Name", username="new_user", password="p" * 12)
                values.update(invalid)
                with self.assertRaises(ValueError):
                    self.service.update_account(1, 2, **values)
                self.assertEqual((self.target.name, self.target.username, self.target.password_hash),
                                 ("Student", "student", "original-hash"))
        self.repository.update.assert_not_called()
        self.passwords.hash_password.assert_not_called()


    # Tests that an unrecognized new role leaves the existing role unchanged without saving.
    def test_invalid_role_change_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.change_role(1, 2, "unknown")
        self.assertEqual(self.target.role, "base_specialist")
        self.repository.update.assert_not_called()


class TestAccountListing(unittest.TestCase):
    # Tests that listing delegates the actor ID and returns only ID, name, username, role, and status.
    def test_listing_returns_display_fields_only(self):
        user = User(id=1, name="Specialist", username="specialist", role="steam_specialist",
                    password_hash="must-not-be-returned", is_active=True)
        service = Mock(spec=AccountService)
        service.list_accounts.return_value = [user]
        with patch("database.account_operations.SessionLocal"), patch(
            "database.account_operations._make_service", return_value=service
        ):
            self.assertEqual(list_accounts(1), [(1, "Specialist", "specialist", "steam_specialist", True)])
        service.list_accounts.assert_called_once_with(1)
