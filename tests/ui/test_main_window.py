# Tests default window behavior and login/logout workflows with dialogs mocked.

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit
from shiboken6 import isValid
from login_dialog import LoginDialog
from sage_apps.account_management_app import AccountManagementDialog
from main import SageWindow
from sage_apps import gcode_display_print_app as gcode_app


class TestStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    # Tests opening/closing SAGE, anonymous Student Mode, and default application-button availability.
    def test_student_mode_defaults(self):
        window = SageWindow(camera_controls=False)
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
        window = SageWindow(camera_controls=False)
        self.addCleanup(window.close)
        window.show()
        with patch("main.QApplication.quit") as quit_app:
            QTest.keyClick(window, Qt.Key.Key_Escape)
            quit_app.assert_called_once_with()


class TestGcodeNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        for name in ("a.gcode", "b.gcode"):
            (folder / name).write_text("G1 X0 Y0\nG1 X10 Y10\n", encoding="utf-8")
        for name, value in (("GCODE_DIR", folder), ("THUMB_DIR", folder / "thumbnails")):
            setting = patch.object(gcode_app, name, value)
            setting.start()
            self.addCleanup(setting.stop)
        self.window = SageWindow(camera_controls=False)
        self.addCleanup(self.close_window)
        self.window.show()
        self.app.processEvents()

    def close_window(self):
        self.window.close()
        viewer = self.window.gcode_window
        if viewer is not None:
            viewer.preview_loader.cancel()
            thread = viewer.preview_loader.thread
            if thread is not None:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
        self.app.processEvents()

    # Tests Student Mode can open the viewer and Home restores the same SAGE window and selection.
    def test_home_preserves_selection(self):
        self.assertIsNone(self.window.gcode_window)
        self.window.app_buttons[1].click()
        viewer = self.window.gcode_window
        self.assertTrue(viewer.isVisible())
        self.assertFalse(self.window.isVisible())
        viewer.next_button.click()
        viewer.home_button.click()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(viewer.isVisible())
        self.assertEqual(self.window.session_state.mode, "student")
        self.window.app_buttons[1].click()
        self.assertIs(self.window.gcode_window, viewer)
        self.assertTrue(viewer.isVisible())
        self.assertEqual(viewer.filename_label.text(), "b.gcode")

    # Tests the viewer window's close button returns home without changing the authenticated session.
    def test_viewer_close_preserves_staff_session(self):
        self.window.session_state = self.window.session_service.log_in(
            user_id=7, user_name="Staff User", role="boss_admin")
        self.window.mode_button.setText(self.window.session_state.button_label)
        self.window.app_buttons[0].setEnabled(True)
        session = self.window.session_state
        self.window.app_buttons[1].click()
        self.window.gcode_window.close()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.gcode_window.isVisible())
        self.assertIs(self.window.session_state, session)
        self.assertEqual(self.window.mode_button.text(), "Boss Admin")
        self.assertTrue(self.window.app_buttons[0].isEnabled())

    # Tests closing SAGE while the viewer is open hides both windows without reopening home.
    def test_closing_sage_hides_viewer(self):
        self.window.app_buttons[1].click()
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.gcode_window.isVisible())


ROLES = (
    ("boss_admin", "Boss Admin"),
    ("steam_specialist", "STEAM Specialist"),
    ("base_specialist", "Work_Study Assistant"),
)


@pytest.mark.parametrize("finish", ["cancel", "escape", "close", "accept"])
def test_repeated_login_dialogs_clear_password_and_are_deleted(finish):
    app = QApplication.instance() or QApplication([])
    window = SageWindow(camera_controls=False)
    original_exec = LoginDialog.exec
    dialogs, cleared = [], []

    def run(dialog):
        dialogs.append(dialog)
        def dismiss():
            dialog.password_input.setText("synthetic unsent password")
            if finish == "accept":
                dialog.user_id, dialog.user_name, dialog.user_role = 7, "Staff", "boss_admin"
                dialog.accept()
            elif finish == "escape":
                QTest.keyClick(dialog, Qt.Key.Key_Escape)
            elif finish == "close":
                dialog.close()
            else:
                dialog.cancel_button.click()
            cleared.append(dialog.password_input.text() == "")
        QTimer.singleShot(0, dismiss)
        return original_exec(dialog)

    try:
        with patch.object(LoginDialog, "exec", run):
            for _ in range(3):
                window.handle_mode_button()
                app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                assert not window.findChildren(LoginDialog)
                assert not isValid(dialogs[-1])
                if finish == "accept":
                    assert window.session_state.user_id == 7
                    assert window.session_state.user_name == "Staff"
                    window.handle_mode_button()  # Log out before the next visit.
                else:
                    assert window.session_state.user_id is None
        assert cleared == [True] * 3
    finally:
        window.close()


@pytest.mark.parametrize("role", [role for role, _ in ROLES])
@pytest.mark.parametrize("finish", ["cancel", "escape", "close", "accept"])
def test_repeated_account_dialogs_clear_all_password_fields_and_are_deleted(role, finish):
    app = QApplication.instance() or QApplication([])
    window = SageWindow(camera_controls=False)
    window.session_state = window.session_service.log_in(7, "Staff", role)
    original_exec = AccountManagementDialog.exec
    dialogs, cleared = [], []

    def run(dialog):
        dialogs.append(dialog)
        def dismiss():
            fields = [field for field in dialog.findChildren(QLineEdit)
                      if field.echoMode() == QLineEdit.EchoMode.Password]
            for field in fields:
                field.setText("synthetic unsent password")
            if finish == "accept":
                dialog.accept()
            elif finish == "escape":
                QTest.keyClick(dialog, Qt.Key.Key_Escape)
            elif finish == "close":
                dialog.close()
            else:
                dialog.close_button.click()
            cleared.append(bool(fields) and all(field.text() == "" for field in fields))
        QTimer.singleShot(0, dismiss)
        return original_exec(dialog)

    try:
        # Form/lifetime test only; worker permissions and cleanup have separate coverage.
        with patch.object(AccountManagementDialog, "_start_operation"), patch.object(
            AccountManagementDialog, "exec", run
        ):
            for _ in range(3):
                window.open_account_management()
                app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                assert not window.findChildren(AccountManagementDialog)
                assert not isValid(dialogs[-1])
        assert cleared == [True] * 3
    finally:
        window.close()


class TestLoginWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = SageWindow(camera_controls=False)
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
    def test_cancel_keeps_student_mode(self):
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
    def test_student_account_access_denied(self):
        with patch("main.AccountManagementDialog", autospec=True) as dialog_class:
            self.window.open_account_management()
            dialog_class.assert_not_called()

    # Tests that account management receives the authenticated ID and role for all staff roles.
    def test_account_dialog_identity(self):
        for role, _label in ROLES:
            with self.subTest(role=role):
                self.log_in(role)
                with patch("main.AccountManagementDialog", autospec=True) as dialog_class:
                    self.window.app_buttons[0].click()
                    dialog_class.assert_called_once_with(actor_id=7, actor_role=role, parent=self.window)
                    dialog_class.return_value.exec.assert_called_once_with()
                self.window.mode_button.click()
