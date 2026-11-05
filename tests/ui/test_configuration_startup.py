# Tests imports, anonymous startup, and login configuration errors in a fresh process.

import os
from pathlib import Path
import subprocess
import sys
import unittest


class TestStudentModeStartup(unittest.TestCase):
    # Fresh processes reject any attempt to import vision dependencies in Home,
    # including valid saved-calibration validation and pointer projection.
    def test_camera_startup_does_not_import_vision_libraries(self):
        script = """
import importlib.abc
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

class RejectVisionImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'cv2', 'numpy', 'mediapipe'}:
            raise AssertionError('GUI imported ' + fullname)
sys.meta_path.insert(0, RejectVisionImports())

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from main import SageWindow
from TouchControls.calibration import Calibration, target_points
from TouchControls.camera_worker import CameraWorker

app = QApplication([])
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'calibration.json'
    screen = app.primaryScreen()
    rect = screen.geometry()
    geometry = (rect.x(), rect.y(), rect.width(), rect.height())
    if mode == 'valid':
        Calibration(0, (640, 480), geometry, screen.devicePixelRatio(),
                    [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                    target_points(rect.width(), rect.height()), [0] * 5).save(path)
    elif mode == 'invalid':
        path.write_text('{invalid json', encoding='utf-8')
    load = Calibration.load
    ticks = []
    with patch.object(Calibration, 'load', side_effect=lambda *_: load(path)), patch.object(
        CameraWorker, 'start'
    ) as start, patch.object(SageWindow, 'show_camera_error') as error:
        window = SageWindow()
        QTimer.singleShot(0, lambda: ticks.append(True))
        window.show()
        app.processEvents()
        app.processEvents()
        assert ticks
        assert window._camera_start_attempted
        if mode == 'valid':
            start.assert_called_once()
            error.assert_not_called()
            assert window.camera_controller.calibration.map_point((100, 100)) == (100, 100)
        else:
            start.assert_not_called()
            error.assert_called_once()
        assert not {'cv2', 'numpy', 'mediapipe'} & sys.modules.keys()
        window.camera_controller.on_finished()
        window.close()
"""
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        for mode in ("missing", "invalid", "valid"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [sys.executable, "-B", "-c", "mode = " + repr(mode) + "\n" + script],
                    cwd=Path(__file__).resolve().parents[2], env=environment,
                    capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # Tests no credentials are read on startup and missing settings recover on a real login thread.
    def test_without_database_config(self):
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
    window = SageWindow(camera_controls=False)
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
