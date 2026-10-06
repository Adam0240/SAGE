# Tests account forms and threaded failure recovery with database calls mocked.

import time, unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox
from sage_apps.account_management_app import AccountManagementDialog
from sqlalchemy.exc import IntegrityError


SELF = (1, "Specialist", "specialist", "steam_specialist", True)


STUDENT = (2, "Student", "student", "base_specialist", True)


class TestAccountDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patcher = patch.object(AccountManagementDialog, "_start_operation")
        self.operation = patcher.start()
        self.addCleanup(patcher.stop)
        self.dialog = AccountManagementDialog(1, "steam_specialist")
        self.addCleanup(self.dialog.close)

    # Tests that boss/specialist role choices are correct and students cannot create accounts.
    def test_role_specific_account_controls(self):
        self.assertEqual([self.dialog.tabs.tabText(i) for i in range(self.dialog.tabs.count())],
                         ["Create Account", "Manage Existing Accounts"])
        self.assertEqual(self.dialog.role_input.count(), 1)
        self.assertEqual(self.dialog.role_input.currentData(), "base_specialist")
        self.operation.assert_called_once_with("list")
        boss = AccountManagementDialog(4, "boss_admin")
        self.addCleanup(boss.close)
        self.assertEqual(boss.tabs.count(), 2)
        self.assertEqual([boss.role_input.itemData(i) for i in range(3)],
                         ["boss_admin", "steam_specialist", "base_specialist"])
        student = AccountManagementDialog(2, "base_specialist")
        self.addCleanup(student.close)
        self.assertFalse(student.create_button.isEnabled())

    # Tests the shared self-password form, identity locks, mismatch rejection, and self-deletion block.
    def test_specialist_self_password_form(self):
        self.dialog._show_accounts([SELF, STUDENT])
        self.assertTrue(self.dialog.edit_name_input.isReadOnly())
        self.assertTrue(self.dialog.edit_username_input.isReadOnly())
        self.assertFalse(self.dialog.delete_button.isEnabled())
        self.operation.reset_mock()
        self.dialog.confirm_delete()
        self.operation.assert_not_called()
        self.dialog.edit_password_input.setText("long-test-password")
        self.dialog.edit_confirm_input.setText("different")
        self.dialog.update_button.click()
        self.operation.assert_not_called()
        self.dialog.edit_confirm_input.setText("long-test-password")
        self.dialog.update_button.click()
        self.operation.assert_called_once_with("update", target_id=1, password="long-test-password")
        self.dialog.account_input.setCurrentIndex(1)
        self.assertFalse(self.dialog.edit_name_input.isReadOnly())
        self.assertFalse(self.dialog.edit_username_input.isReadOnly())
        self.assertTrue(self.dialog.delete_button.isEnabled())

    # Tests that student creation rejects mismatched passwords and submits the permitted student role.
    def test_create_student_form(self):
        self.dialog.name_input.setText("New Student")
        self.dialog.username_input.setText("new_student")
        self.dialog.password_input.setText("long-test-password")
        self.dialog.confirm_input.setText("different")
        self.operation.reset_mock()
        self.dialog.create_button.click()
        self.operation.assert_not_called()
        self.dialog.confirm_input.setText("long-test-password")
        self.dialog.create_button.click()
        self.operation.assert_called_once_with("create", name="New Student", username="new_student",
                                               password="long-test-password", role="base_specialist")

    # Tests that student edits submit identity changes and preserve the password when left blank.
    def test_update_student_form(self):
        self.dialog._show_accounts([STUDENT])
        self.dialog.edit_name_input.setText("Updated Student")
        self.operation.reset_mock()
        self.dialog.update_button.click()
        self.operation.assert_called_once_with("update", target_id=2, name="Updated Student",
                                               username="student", password=None)

    # Tests that student deletion is submitted only after the user confirms the selected account.
    def test_delete_student_requires_confirmation(self):
        self.dialog._show_accounts([STUDENT])
        self.operation.reset_mock()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.dialog.delete_button.click()
        self.operation.assert_not_called()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.dialog.delete_button.click()
        self.operation.assert_called_once_with("delete", target_id=2)

    # Tests that empty or failed account listings disable changes and discard stale account selections.
    def test_unavailable_accounts_disable_management(self):
        self.dialog._show_accounts([])
        self.assertFalse(self.dialog.update_button.isEnabled())
        self.assertFalse(self.dialog.delete_button.isEnabled())
        self.dialog._show_accounts([STUDENT])
        self.dialog._thread = Mock(spec=QThread)
        self.dialog._operation = "list"
        self.dialog._result = ("error", "Database unavailable. Try again later.")
        self.dialog._finish_operation()
        self.assertEqual(self.dialog.account_input.count(), 0)
        self.assertFalse(self.dialog.update_button.isEnabled())
        self.assertFalse(self.dialog.delete_button.isEnabled())


class TestAccountThreadLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for_worker(self, dialog):
        deadline = time.monotonic() + 5
        while dialog._thread is not None and time.monotonic() < deadline:
            self.app.processEvents()
            # Release Python's GIL so the worker can execute its Python slot.
            time.sleep(0.01)
        self.assertIsNone(dialog._thread, "Account worker did not finish within five seconds")

    def close_dialog(self, dialog):
        # Drain queued signals before closing so a failing assertion cannot destroy a running thread.
        self.wait_for_worker(dialog)
        dialog.close()

    # Tests real QThread signal delivery, successful listing, duplicate-update recovery, and retry success.
    def test_worker_finishes_and_dialog_recovers_after_failure(self):
        accounts = [(1, "Specialist", "specialist", "steam_specialist", True),
                    (2, "Student", "student", "base_specialist", True)]
        with patch("sage_apps.account_management_app.list_accounts", return_value=accounts), patch(
            "sage_apps.account_management_app.update_account"
        ) as update:
            dialog = AccountManagementDialog(1, "steam_specialist")
            self.addCleanup(self.close_dialog, dialog)
            self.assertFalse(dialog.tabs.isEnabled())
            self.wait_for_worker(dialog)
            self.assertTrue(dialog.tabs.isEnabled())
            self.assertIsNone(dialog._worker)
            self.assertEqual(dialog.account_input.count(), 2)
            dialog.account_input.setCurrentIndex(dialog.account_input.findData(2))
            dialog.edit_name_input.setText("Updated Student")
            update.side_effect = IntegrityError("update", {}, Exception("duplicate"))
            dialog.update_button.click()
            self.assertFalse(dialog.tabs.isEnabled())
            self.wait_for_worker(dialog)
            self.assertTrue(dialog.tabs.isEnabled())
            self.assertTrue(dialog.update_button.isEnabled())
            self.assertIn("username is already in use", dialog.status_label.text())
            self.assertIsNone(dialog._worker)

            update.side_effect = None
            dialog.update_button.click()
            self.wait_for_worker(dialog)
            self.assertTrue(dialog.tabs.isEnabled())
            self.assertEqual(dialog.status_label.text(), "Account updated.")
            self.assertEqual(update.call_count, 2)
