# Tests default window behavior and login/logout workflows with dialogs mocked.

import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from main import SageWindow


class TestStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    # Tests opening/closing SAGE, anonymous Student Mode, and default application-button availability.
    def test_default_window_behavior(self):
        window = SageWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertEqual(window.windowTitle(), "SAGE")
        self.assertEqual(window.session_state.mode, "student")
        self.assertIsNone(window.session_state.user_id)
        self.assertIsNone(window.session_state.user_name)
        self.assertEqual(window.mode_button.text(), "Student Mode")
        self.assertTrue(window.mode_button.isEnabled())
        self.assertEqual(len(window.app_buttons), 3)
        self.assertTrue(all(button.isVisible() for button in window.app_buttons))
        self.assertFalse(window.app_buttons[0].isEnabled())
        self.assertTrue(all(button.isEnabled() for button in window.app_buttons[1:]))
        window.close()
        self.app.processEvents()
        self.assertFalse(window.isVisible())

    # Tests that pressing Escape requests application shutdown exactly once.
    def test_escape_requests_exit(self):
        window = SageWindow()
        self.addCleanup(window.close)
        window.show()
        with patch("main.QApplication.quit") as quit_app:
            QTest.keyClick(window, Qt.Key.Key_Escape)
            quit_app.assert_called_once_with()


ROLES = (
    ("boss_admin", "Boss Admin"),
    ("steam_specialist", "STEAM Specialist"),
    ("base_specialist", "Work_Study Assistant"),
)


class TestLoginWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = SageWindow()
        self.addCleanup(self.window.close)

    def log_in(self, role):
        with patch("main.LoginDialog", autospec=True) as dialog_class:
            dialog_class.DialogCode.Accepted = QDialog.DialogCode.Accepted
            dialog = dialog_class.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.user_id, dialog.user_name, dialog.user_role = 7, "Staff User", role
            self.window.mode_button.click()
            dialog.exec.assert_called_once_with()

    # Tests that successful login for each staff role sets identity, mode label, and account access.
    def test_successful_login_for_all_roles(self):
        for role, label in ROLES:
            with self.subTest(role=role):
                self.log_in(role)
                self.assertEqual(self.window.session_state.mode, role)
                self.assertEqual(self.window.session_state.user_id, 7)
                self.assertEqual(self.window.session_state.user_name, "Staff User")
                self.assertEqual(self.window.mode_button.text(), label)
                self.assertTrue(self.window.app_buttons[0].isEnabled())
                self.window.mode_button.click()

    # Tests that cancelling login preserves anonymous Student Mode and disabled account access.
    def test_cancelled_login_stays_in_student_mode(self):
        with patch("main.LoginDialog", autospec=True) as dialog_class:
            dialog_class.DialogCode.Accepted = QDialog.DialogCode.Accepted
            dialog_class.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.window.mode_button.click()
        self.assertEqual(self.window.session_state.mode, "student")
        self.assertIsNone(self.window.session_state.user_id)
        self.assertIsNone(self.window.session_state.user_name)
        self.assertEqual(self.window.mode_button.text(), "Student Mode")
        self.assertFalse(self.window.app_buttons[0].isEnabled())

    # Tests that logout for every staff role clears identity and disables account access without login.
    def test_logout_for_all_roles(self):
        for role, _label in ROLES:
            with self.subTest(role=role):
                self.log_in(role)
                with patch("main.LoginDialog", autospec=True) as dialog_class:
                    self.window.mode_button.click()
                    dialog_class.assert_not_called()
                self.assertEqual(self.window.session_state.mode, "student")
                self.assertIsNone(self.window.session_state.user_id)
                self.assertIsNone(self.window.session_state.user_name)
                self.assertEqual(self.window.mode_button.text(), "Student Mode")
                self.assertFalse(self.window.app_buttons[0].isEnabled())

    # Tests that anonymous callers cannot open the account dialog even by calling its handler directly.
    def test_student_mode_cannot_open_account_management(self):
        with patch("main.AccountManagementDialog", autospec=True) as dialog_class:
            self.window.open_account_management()
            dialog_class.assert_not_called()

    # Tests that account management receives the authenticated ID and role for all staff roles.
    def test_account_dialog_receives_authenticated_identity(self):
        for role, _label in ROLES:
            with self.subTest(role=role):
                self.log_in(role)
                with patch("main.AccountManagementDialog", autospec=True) as dialog_class:
                    self.window.app_buttons[0].click()
                    dialog_class.assert_called_once_with(actor_id=7, actor_role=role, parent=self.window)
                    dialog_class.return_value.exec.assert_called_once_with()
                self.window.mode_button.click()
