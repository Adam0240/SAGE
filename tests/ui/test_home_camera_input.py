from types import SimpleNamespace
import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtWidgets import QApplication, QDialog

from main import SageWindow
from TouchControls.calibration import Calibration, target_points
from TouchControls.home_input import HomeInputController


class FakeWorker(QObject):
    observation = Signal(object, object, float)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, camera, model, parent):
        super().__init__(parent)
        self.camera = camera
        self.stop_requested = False

    def start(self):
        pass

    def requestInterruption(self):
        self.stop_requested = True

    def wait(self):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    clock = [time.monotonic()]
    monkeypatch.setattr("TouchControls.home_input.time.monotonic", lambda: clock[0])
    window = SageWindow()
    window.show()
    window.activateWindow()
    app.processEvents()
    path = tmp_path / "calibration.json"
    Calibration(2, (1920, 1080), (0, 0, 1920, 1080), 1,
                [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                target_points(1920, 1080), [0] * 5).save(path)
    controller = HomeInputController(window, calibration_path=path, worker_factory=FakeWorker)
    monkeypatch.setattr(controller, "geometry", lambda: ((0, 0, 1920, 1080), 1))
    window.camera_controller = controller
    controller.status_changed.connect(window.camera_status.setText)
    controller.stopped.connect(window.camera_stopped)
    controller.start()
    state = SimpleNamespace(app=app, window=window, controller=controller, clock=clock, path=path)
    yield state
    controller.stop()
    if controller.worker is not None:
        controller.worker.finished.emit()
    window.close()
    window.deleteLater()
    app.processEvents()


def observe(state, point, count=1, size=(1920, 1080)):
    for _ in range(count):
        state.clock[0] += 0.1
        state.controller.on_observation(point, size, state.clock[0])


def center(button):
    point = button.mapToGlobal(button.rect().center())
    return point.x(), point.y()


def test_dwell_opens_guide_once_and_home_requires_new_dwell(setup):
    s = setup
    point = center(s.window.app_buttons[2])
    observe(s, point, 10)
    assert s.window.steamguide_window is None
    observe(s, point, 2)
    guide = s.window.steamguide_window
    assert guide.isVisible() and not s.window.isVisible()
    assert not s.controller.overlay.isVisible()
    observe(s, point, 20)
    assert guide.isVisible()
    guide.home_button.click()
    s.app.processEvents()
    observe(s, point, 5)
    assert s.window.isVisible()
    observe(s, point, 7)
    assert guide.isVisible()


def test_disabled_and_circle_corner_buttons_do_not_activate(setup):
    s = setup
    button = s.window.app_buttons[0]
    click = Mock()
    button.clicked.connect(click)
    observe(s, center(button), 20)
    click.assert_not_called()
    button.setEnabled(True)
    corner = button.mapToGlobal(QPoint(1, 1))
    observe(s, (corner.x(), corner.y()), 20)
    click.assert_not_called()


def test_tracker_loss_and_stale_data_cancel_pending_activation(setup):
    s = setup
    point = center(s.window.app_buttons[2])
    observe(s, point, 7)
    observe(s, None)
    observe(s, point, 7)
    assert s.window.steamguide_window is None
    s.clock[0] += 1
    s.controller.check_idle()
    assert not s.controller.overlay.isVisible()
    s.controller.on_observation(point, (1920, 1080), s.clock[0] - 0.5)
    assert s.window.steamguide_window is None
    observe(s, point, 7)
    assert s.window.steamguide_window is None


def test_dialogs_and_explicit_suspension_block_activation(setup):
    s = setup
    point = center(s.window.app_buttons[2])
    dialog = QDialog(s.window)
    dialog.setModal(True)
    dialog.show()
    s.app.processEvents()
    observe(s, point, 20)
    assert s.window.steamguide_window is None
    dialog.close()
    s.window.activateWindow()
    s.app.processEvents()
    with s.controller.suspended():
        observe(s, point, 20)
    observe(s, point, 5)
    assert s.window.steamguide_window is None


def test_window_offset_is_applied_to_calibrated_coordinates(setup):
    s = setup
    s.window.move(100, 70)
    s.app.processEvents()
    point = center(s.window.app_buttons[2])
    observe(s, point, 12)
    assert s.window.steamguide_window.isVisible()


def test_resolution_change_stops_input_and_requests_recalibration(setup):
    s = setup
    worker = s.controller.worker
    observe(s, center(s.window.app_buttons[2]), size=(640, 480))
    assert not s.controller.enabled
    assert worker.stop_requested
    assert "calibration again" in s.window.camera_status.text()


def test_display_scale_change_stops_input(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(s.controller, "geometry", lambda: ((0, 0, 1920, 1080), 1.5))
    observe(s, center(s.window.app_buttons[2]))
    assert not s.controller.enabled


def test_missing_or_invalid_calibration_does_not_open_camera(setup):
    s = setup
    s.controller.stop()
    s.controller.worker.finished.emit()
    s.controller.worker_factory = Mock()
    for contents in (None, "not json"):
        if contents is None:
            s.path.unlink()
        else:
            s.path.write_text(contents)
        s.controller.start()
        assert not s.controller.enabled
        assert "unavailable" in s.window.camera_status.text()
    s.controller.worker_factory.assert_not_called()


def test_disable_and_camera_error_clear_pointer(setup):
    s = setup
    observe(s, center(s.window.app_buttons[2]), 3)
    worker = s.controller.worker
    worker.failed.emit("Camera disconnected")
    assert not s.controller.enabled
    assert not s.controller.overlay.isVisible()
    assert worker.stop_requested
    worker.finished.emit()
    assert s.controller.worker is None
    assert s.window.camera_button.text() == "Enable camera"
    assert "disconnected" in s.window.camera_status.text()


def test_closing_home_waits_for_camera_cleanup(setup):
    s = setup
    worker = s.controller.worker
    assert not s.window.close()
    assert worker.stop_requested
    worker.finished.emit()
    assert not s.window.isVisible()


def test_mode_dwell_opens_login_once_and_logout_does_not_repeat(setup):
    s = setup
    with patch("main.LoginDialog", autospec=True) as dialog:
        dialog.DialogCode.Accepted = QDialog.DialogCode.Accepted
        dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
        observe(s, center(s.window.mode_button), 12)
        dialog.return_value.exec.assert_called_once()
        assert s.window.session_state.mode == "student"
    s.controller.reset()
    s.window.session_state = s.window.session_service.log_in(
        user_id=7, user_name="Staff", role="boss_admin")
    s.window.mode_button.setText("Boss Admin")
    with patch("main.LoginDialog", autospec=True) as dialog:
        observe(s, center(s.window.mode_button), 30)
        assert s.window.session_state.mode == "student"
        dialog.assert_not_called()


def test_disable_button_can_be_selected_by_dwell(setup):
    s = setup
    worker = s.controller.worker
    observe(s, center(s.window.camera_button), 12)
    assert not s.controller.enabled
    assert worker.stop_requested
    assert not s.window.camera_button.isEnabled()
    worker.finished.emit()
    assert s.window.camera_button.isEnabled()
    assert s.window.camera_status.text() == "Camera controls off"
