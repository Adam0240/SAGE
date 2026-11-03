import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

from TouchControls.calibration import Calibration
from TouchControls.hand_calibration import CalibrationWindow, CameraWorker
from TouchControls.camera_worker import capture_process


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
    connection = Mock()
    connection.poll.return_value = False
    with patch("TouchControls.camera_manager.CameraManager", return_value=camera):
        capture_process(connection, 0, "test.task")
    connection.send.assert_called_once_with(("error", "Camera disconnected"))
    connection.close.assert_called_once()
    camera.__exit__.assert_called_once()


def simulated_capture(connection, mode, model_path):
    """Spawnable fake driver: signal readiness, then cooperate, fail, or hang."""
    if mode == 4:
        time.sleep(60)  # Camera opening never produces the first observation.
    connection.send(("observation", (10.0, 20.0), (640, 480), time.monotonic()))
    if mode == 1:
        connection.send(("error", "Camera disconnected"))
        connection.close()
        return
    if mode == 2:
        connection.close()
        return
    if mode == 3:
        connection.recv()
        connection.close()
        return
    # Simulate a native call that does not honor the stop request.
    time.sleep(60)


def wait_until(app, condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert condition()


@pytest.mark.parametrize("mode", [0, 1, 2, 3])
def test_process_shutdown_and_failures_keep_event_loop_responsive(mode):
    app = QApplication.instance() or QApplication([])
    worker = CameraWorker(mode, "unused", process_target=simulated_capture,
                          stop_timeout=0.1)
    observations, failures, completed, ticks = [], [], [], []
    worker.observation.connect(lambda *value: observations.append(value))
    worker.failed.connect(failures.append)
    worker.finished.connect(lambda: completed.append(True))
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(True))
    heartbeat.start()
    try:
        worker.start()
        if mode in (0, 3):
            wait_until(app, lambda: bool(observations))
            assert observations[0][:2] == ((10.0, 20.0), (640, 480))
        before = len(ticks)
        started = time.monotonic()
        if mode in (0, 3):
            worker.requestInterruption()
            worker.requestInterruption()  # Repeated closes must not extend grace.
        wait_until(app, lambda: bool(completed), timeout=3)
        assert time.monotonic() - started < 3
        assert completed == [True]
        assert not worker.isRunning()
        assert worker.connection is None
        if mode == 0:
            assert len(ticks) > before + 2
            assert worker.terminated
        assert failures == (["Camera disconnected"] if mode == 1 else
                            ["Camera tracking process stopped unexpectedly."] if mode == 2 else [])
    finally:
        heartbeat.stop()
        assert worker.wait()


@pytest.mark.parametrize("phase", ["startup", "frame", "quit"])
def test_camera_deadlines_and_application_quit_are_bounded(phase):
    app = QApplication.instance() or QApplication([])
    worker = CameraWorker(4 if phase == "startup" else 0, "unused",
                          process_target=simulated_capture, stop_timeout=0.1,
                          frame_timeout=0.15,
                          startup_timeout=0.15 if phase == "startup" else 30)
    observations, failures, completed = [], [], []
    worker.observation.connect(lambda *value: observations.append(value))
    worker.failed.connect(failures.append)
    worker.finished.connect(lambda: completed.append(True))
    try:
        worker.start()
        if phase != "startup":
            wait_until(app, lambda: bool(observations))
        if phase == "quit":
            started = time.monotonic()
            # No Qt event pumping: exercise the aboutToQuit fallback.
            assert worker.wait()
            assert time.monotonic() - started < 2
            assert not failures
        else:
            wait_until(app, lambda: bool(completed), timeout=3)
            assert len(failures) == 1
            assert "timed out" in failures[0]
        assert completed == [True]
        assert not worker.isRunning()
    finally:
        assert worker.wait()


@pytest.mark.parametrize("mode", [0, 4])
def test_calibration_closes_with_stuck_camera_process(window, mode):
    app = QApplication.instance()
    worker = CameraWorker(mode, "unused", window,
                          process_target=simulated_capture, stop_timeout=0.1)
    window.worker = worker
    worker.finished.connect(window.on_worker_finished)
    observations = []
    worker.observation.connect(lambda *value: observations.append(value))
    try:
        worker.start()
        if mode == 0:
            wait_until(app, lambda: bool(observations))
        assert not window.close()
        assert window.closing
        wait_until(app, lambda: not window.isVisible(), timeout=3)
        assert not worker.isRunning()
    finally:
        assert worker.wait()


def test_process_failure_during_modal_observation_handler():
    from PySide6.QtCore import QEventLoop

    app = QApplication.instance() or QApplication([])
    worker = CameraWorker(0, "unused", process_target=simulated_capture,
                          frame_timeout=0.15, stop_timeout=0.1)
    completed = []
    worker.finished.connect(lambda: completed.append(True))
    returned = []

    def open_modal(*_):
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(3000)
        loop.exec()
        returned.append(True)

    worker.observation.connect(open_modal)
    try:
        worker.start()
        wait_until(app, lambda: bool(returned))
        assert completed == [True]
        assert not worker.isRunning()
    finally:
        assert worker.wait()
