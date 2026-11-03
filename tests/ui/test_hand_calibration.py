import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QApplication

from TouchControls.calibration import Calibration
from TouchControls.hand_calibration import CalibrationWindow, CameraWorker


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = CalibrationWindow(output=tmp_path / "calibration.json", start_camera=False)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def feed(window, point):
    now = time.monotonic()
    window.accept_after = now - 1
    for i in range(15):
        timestamp = now - (14 - i) * 0.03
        with patch("TouchControls.hand_calibration.time.monotonic", return_value=timestamp):
            window.on_observation(point, (1920, 1080), timestamp)


def complete(window):
    for _ in range(9):
        feed(window, window.current_target())
        window.capture()


def test_full_calibration_requires_checks_and_explicit_save(window):
    window.save()
    assert not window.output.exists()
    complete(window)
    assert window.stage == "ready"
    assert not window.output.exists()
    window.save()
    assert window.stage == "saved"
    saved = Calibration.load(window.output)
    assert len(saved.verification_errors) == 5
    assert max(saved.verification_errors) < 0.01


def test_tracking_loss_stale_samples_and_movement_do_not_capture(window):
    window.capture()
    assert not window.points
    feed(window, window.current_target())
    window.on_observation(None, (1920, 1080), time.monotonic())
    window.capture()
    assert not window.points
    feed(window, window.current_target())
    window.last_observed -= 1
    window.capture()
    assert not window.points
    feed(window, window.current_target())
    window.samples[-1] = (window.last_observed, (900, 900))
    window.capture()
    assert not window.points


def test_failed_check_can_retry_and_cancel_preserves_previous_file(window):
    window.output.write_text("previous calibration", encoding="utf-8")
    for _ in range(4):
        feed(window, window.current_target())
        window.capture()
    x, y = window.current_target()
    feed(window, (x + 100, y))
    window.capture()
    assert not window.errors
    assert "Alignment error" in window.message
    feed(window, window.current_target())
    window.capture()
    assert len(window.errors) == 1
    window.restart()
    assert window.stage == "capture"
    assert window.matrix is None
    assert not window.samples
    window.close()
    assert window.output.read_text() == "previous calibration"


def test_resolution_change_disables_capture(window):
    feed(window, window.current_target())
    window.on_observation((100, 100), (640, 480), time.monotonic())
    window.capture()
    assert window.fatal_error
    assert not window.points


def test_save_failure_keeps_ready_state_for_retry(window):
    complete(window)
    with patch.object(Calibration, "save", side_effect=PermissionError("read-only")):
        window.save()
    assert window.stage == "ready"
    assert "Could not save" in window.message
    assert not window.output.exists()


def test_close_requests_worker_stop_before_closing(window):
    window.worker = Mock()
    window.worker.isRunning.return_value = True
    assert not window.close()
    window.worker.requestInterruption.assert_called_once()
    assert window.closing
    window.worker.isRunning.return_value = False
    window.on_worker_finished()
    assert not window.isVisible()


def test_worker_failure_releases_camera_and_emits_error():
    camera = Mock()
    camera.__enter__ = Mock(return_value=camera)
    camera.__exit__ = Mock()
    camera.update.return_value = False
    camera.last_error = "Camera disconnected"
    worker = CameraWorker(0, "test.task")
    errors = []
    worker.failed.connect(errors.append)
    with patch("TouchControls.camera_worker.CameraManager", return_value=camera):
        worker.run()
    assert errors == ["Camera disconnected"]
    camera.__exit__.assert_called_once()
