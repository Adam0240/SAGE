# Tests actual login QThreads and dialog recovery with database/authentication calls mocked.

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QDialog
from sqlalchemy.exc import SQLAlchemyError

from login_dialog import LoginDialog, LoginWorker


class TestLoginThreadLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        session_patcher = patch("login_dialog.SessionLocal")
        self.sessions = session_patcher.start()
        self.addCleanup(session_patcher.stop)
        auth_patcher = patch("login_dialog.AuthenticationService")
        self.authentication = auth_patcher.start().return_value
        self.addCleanup(auth_patcher.stop)
        self.user = SimpleNamespace(id=7, name="Staff User", role="boss_admin")
        self.authentication.authenticate.return_value = self.user
        self.dialog = LoginDialog()
        self.addCleanup(self.close_dialog)
        self.dialog.username_input.setText("staff")
        self.dialog.password_input.setText("long test password")

    def wait_until(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(condition(), "Login worker did not complete within five seconds")

    def close_dialog(self):
        # On a regression, stop an idle worker event loop before destroying its owner.
        thread = self.dialog._thread
        if thread is not None:
            thread.quit()
            self.wait_until(lambda: self.dialog._thread is None)
        self.dialog.close()

    def start_and_wait(self):
        self.dialog.login_button.click()
        thread = self.dialog._thread
        self.assertIsNotNone(thread)
        self.assertFalse(self.dialog.login_button.isEnabled())
        self.wait_until(lambda: self.dialog._thread is None)
        self.assertIsNone(self.dialog._worker)
        self.assertTrue(self.dialog.login_button.isEnabled())
        self.assertEqual(self.dialog.login_button.text(), "Log In")
        self.assertEqual(self.dialog.password_input.text(), "")

    # Tests a real login thread accepts staff identity and closes its database session.
    def test_successful_login_accepts_identity(self):
        self.start_and_wait()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual((self.dialog.user_id, self.dialog.user_name, self.dialog.user_role),
                         (7, "Staff User", "boss_admin"))
        self.authentication.authenticate.assert_called_once_with("staff", "long test password")
        self.sessions.return_value.__exit__.assert_called_once()

    # Tests invalid credentials keep the dialog open and permit a subsequent valid login.
    def test_invalid_credentials_allow_retry(self):
        self.dialog.show()
        self.authentication.authenticate.return_value = None
        self.start_and_wait()
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(self.dialog.error_label.text(), "Invalid username or password.")
        self.assertIsNone(self.dialog.user_id)
        self.authentication.authenticate.return_value = self.user
        self.dialog.password_input.setText("retry password")
        self.start_and_wait()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.authentication.authenticate.call_count, 2)

    # Tests connection, authentication, and session-close exceptions recover with safe errors.
    def test_errors_stop_worker_and_allow_retry(self):
        for source in ("connection", "authentication", "session_close"):
            for error_type in (SQLAlchemyError, RuntimeError):
                with self.subTest(source=source, error=error_type.__name__):
                    error = error_type("sensitive exception detail")
                    target = {
                        "connection": self.sessions,
                        "authentication": self.authentication.authenticate,
                        "session_close": self.sessions.return_value.__exit__,
                    }[source]
                    target.side_effect = error
                    self.dialog.show()
                    self.dialog.password_input.setText("failure password")
                    self.start_and_wait()
                    self.assertTrue(self.dialog.isVisible())
                    self.assertIsNone(self.dialog.user_id)
                    expected = ("Database unavailable. Try again later."
                                if error_type is SQLAlchemyError
                                else "Could not complete login. Try again.")
                    self.assertEqual(self.dialog.error_label.text(), expected)
                    target.side_effect = None
                    self.dialog.password_input.setText("retry password")
                    self.start_and_wait()
                    self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
                    self.assertEqual(self.dialog.error_label.text(), "")
                    # A fresh dialog prevents previous accepted identity masking a failure.
                    self.dialog.close()
                    self.dialog = LoginDialog()
                    self.dialog.username_input.setText("staff")

    # Tests exactly one completion signal, including failures during session cleanup.
    def test_worker_emits_one_result_after_session_closes(self):
        for error in (None, SQLAlchemyError("close failed"), RuntimeError("close failed")):
            with self.subTest(error=type(error).__name__):
                context = MagicMock()
                results = []
                events = []
                def close_session(*_args):
                    events.append("session_closed")
                    if error is not None:
                        raise error
                context.__exit__.side_effect = close_session
                worker = LoginWorker("staff", "private password")
                worker.completed.connect(lambda result: (events.append("completed"), results.append(result)))
                with patch("login_dialog.SessionLocal", return_value=context):
                    worker.run()
                self.assertEqual(events, ["session_closed", "completed"])
                expected = "success" if error is None else (
                    "database_error" if isinstance(error, SQLAlchemyError) else "error")
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0][0], expected)
                self.assertEqual(worker.password, "")

    # Tests an actually stopped thread with no result still restores the dialog for retry.
    def test_missing_result_restores_controls(self):
        def stop_without_result(worker):
            worker.thread().quit()
        with patch.object(LoginWorker, "run", stop_without_result):
            self.start_and_wait()
        self.assertEqual(self.dialog.error_label.text(), "Could not complete login. Try again.")
        self.assertIsNone(self.dialog.user_id)
        self.dialog.password_input.setText("retry password")
        self.start_and_wait()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)

    # Tests close/Escape and repeated submissions cannot destroy or duplicate a running worker.
    def test_active_login_blocks_close_and_duplicate_attempts(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        worker_threads = []
        def delayed_authentication(*_args):
            worker_threads.append(QThread.currentThread())
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release authentication")
            return None
        self.authentication.authenticate.side_effect = delayed_authentication
        self.dialog.show()
        self.dialog.attempt_login()
        thread = self.dialog._thread
        self.wait_until(entered.is_set)
        self.assertFalse(self.dialog.close())
        self.dialog.reject()
        self.assertTrue(self.dialog.isVisible())
        self.dialog.attempt_login()
        self.assertIs(self.dialog._thread, thread)
        self.authentication.authenticate.assert_called_once()
        self.assertEqual(worker_threads, [thread])
        self.assertNotEqual(thread, self.app.thread())
        release.set()
        self.wait_until(lambda: self.dialog._thread is None)
        self.assertTrue(self.dialog.close())
        self.assertFalse(self.dialog.isVisible())
