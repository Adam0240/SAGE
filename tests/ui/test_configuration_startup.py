# Tests imports, anonymous startup, and login configuration errors in a fresh process.

import os
from pathlib import Path
import subprocess
import sys
import unittest


class TestUnconfiguredStartup(unittest.TestCase):
    # Tests no credentials are read on startup and missing settings recover on a real login thread.
    def test_student_mode_opens_without_database_configuration(self):
        script = """
import time
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
with patch('dotenv.dotenv_values', return_value={}) as settings, patch(
    'sqlalchemy.create_engine', side_effect=AssertionError('Unexpected engine creation')
):
    from main import SageWindow
    from login_dialog import LoginDialog
    app = QApplication([])
    window = SageWindow()
    window.show()
    app.processEvents()
    assert window.isVisible()
    assert window.session_state.mode == 'student'
    settings.assert_not_called()
    dialog = LoginDialog(window)
    dialog.username_input.setText('staff')
    dialog.password_input.setText('test password')
    dialog.attempt_login()
    deadline = time.monotonic() + 5
    while dialog._thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert dialog._thread is None
    assert dialog.login_button.isEnabled()
    assert dialog.user_id is None
    assert 'POSTGRES_PASSWORD' in dialog.error_label.text()
    assert '.env.example' in dialog.error_label.text()
    assert dialog.password_input.text() == ''
    dialog.close()
    window.close()
"""
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("POSTGRES_")}
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
