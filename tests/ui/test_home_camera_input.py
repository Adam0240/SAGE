from types import SimpleNamespace
import time
import warnings
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Signal, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton, QLineEdit, QListWidget, QComboBox, QTextBrowser, QWidget

from main import SageWindow
from TouchControls.calibration import Calibration, target_points
from TouchControls.home_input import HomeInputController
from TouchControls.widgets import TouchChoices


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
    clock = [1000.0]
    # Replace only the controller's clock, not time.monotonic process-wide.
    monkeypatch.setattr("TouchControls.home_input.time",
                        SimpleNamespace(monotonic=lambda: clock[0]))
    window = SageWindow(camera_controls=False)
    window.show()
    app.processEvents()
    set_test_active_window(window)
    path = tmp_path / "calibration.json"
    Calibration(2, (1920, 1080), (0, 0, 1920, 1080), 1,
                [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                target_points(1920, 1080), [0] * 5).save(path)
    controller = HomeInputController(window, calibration_path=path, worker_factory=FakeWorker)
    monkeypatch.setattr(controller, "geometry", lambda: ((0, 0, 1920, 1080), 1))
    window.camera_controller = controller
    statuses = []
    controller.status_changed.connect(statuses.append)
    controller.stopped.connect(window.camera_stopped)
    controller.start()
    state = SimpleNamespace(app=app, window=window, controller=controller, clock=clock, path=path, statuses=statuses)
    activate_window(state, window)
    yield state
    controller.stop()
    if controller.worker is not None:
        controller.worker.finished.emit()
    window.close()
    window.deleteLater()
    # Remove old windows and their application event filters before the next test.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def observe(state, point, count=1, size=(1920, 1080)):
    for _ in range(count):
        state.clock[0] += 0.1
        state.controller.on_observation(point, size, state.clock[0])


def center(button):
    point = button.mapToGlobal(button.rect().center())
    return point.x(), point.y()


def input_state(s):
    controller = s.controller
    return {
        "active": QApplication.activeWindow(),
        "modal": QApplication.activeModalWidget(),
        "popup": QApplication.activePopupWidget(),
        "current": controller.current_window(),
        "surface": controller.surface,
        "enabled": controller.enabled,
        "pause_depth": controller.pause_depth,
        "target": controller.dwell.target,
        "locked": controller.dwell.locked,
        "progress": controller.dwell.progress,
        "clock": s.clock[0],
        "accept_after": controller.accept_after,
        "last_timestamp": controller.last_timestamp,
    }


def set_test_active_window(window):
    # Qt deprecated this in favor of native activation requests, but tests need
    # synchronous Qt focus state even when the offscreen OS request is ignored.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning,
                                message=r"Function: 'QApplication\.setActiveWindow")
        QApplication.setActiveWindow(window)


def activate_window(s, window):
    # Drain layout/native events, then synchronously establish Qt's active window.
    # activateWindow() only requests OS focus, which offscreen CI may never grant.
    # Keep current_window() real so ownership, modal and popup checks still apply.
    s.app.processEvents()
    assert window.isVisible(), input_state(s)
    set_test_active_window(window)
    assert QApplication.activeWindow() is window, input_state(s)
    selected = s.controller.current_window()
    assert selected is (window if s.controller.owns(window) else None), input_state(s)
    s.controller.use_window(selected)


def test_dwell_opens_guide_once_and_home_requires_new_dwell(setup):
    s = setup
    point = center(s.window.app_buttons[2])
    observe(s, point, 10)
    assert s.window.steamguide_window is None
    assert 0 < s.controller.dwell.progress < 1, input_state(s)
    observe(s, point, 2)
    guide = s.window.steamguide_window
    assert guide.isVisible() and not s.window.isVisible()
    assert not s.controller.overlay.isVisible()
    observe(s, point, 20)
    assert guide.isVisible()
    guide.home_button.click()
    activate_window(s, s.window)
    observe(s, point, 5)
    assert s.window.isVisible()
    assert 0 < s.controller.dwell.progress < 1, input_state(s)
    observe(s, point, 7)
    assert guide.isVisible(), input_state(s)


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
    activate_window(s, s.window)
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
    assert "calibration again" in s.statuses[-1]


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
        assert "unavailable" in s.statuses[-1]
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
    assert "disconnected" in s.statuses[-1]


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


def test_default_startup_starts_camera_once_without_controls():
    app = QApplication.instance() or QApplication([])
    controller = Mock()
    controller.worker = None
    with patch("TouchControls.home_input.HomeInputController", return_value=controller) as factory:
        window = SageWindow()
        try:
            factory.assert_not_called()
            window.show()
            app.processEvents()
            factory.assert_called_once_with(window)
            controller.start.assert_called_once()
            assert not hasattr(window, "camera_button")
            assert not hasattr(window, "camera_status")
            assert len(window.findChildren(QPushButton)) == 4
            window.hide()
            window.show()
            app.processEvents()
            controller.start.assert_called_once()
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()


def test_closing_before_startup_does_not_open_camera():
    app = QApplication.instance() or QApplication([])
    with patch("TouchControls.home_input.HomeInputController") as factory:
        window = SageWindow()
        window.show()
        window.close()
        app.processEvents()
        factory.assert_not_called()
        window.deleteLater()
        app.processEvents()


def test_camera_failure_has_dismissible_dialog_instead_of_status_row(setup):
    s = setup
    s.window.show_camera_error("Camera disconnected")
    s.app.processEvents()
    dialog = s.window.findChild(QMessageBox)
    assert dialog.isVisible()
    assert "Camera disconnected" in dialog.text()
    assert "Mouse and keyboard" in dialog.text()
    dialog.accept()
    s.app.processEvents()
    assert s.window.isVisible()


def dwell_widget(s, widget):
    activate_window(s, widget.window())
    assert s.controller.active(), input_state(s)
    assert widget.isVisible() and widget.isEnabled(), input_state(s)
    local = widget.mapTo(widget.window(), widget.rect().center())
    target = s.controller.target_at((local.x(), local.y()))
    assert target is not None and target[0] is widget, input_state(s)
    point = center(widget)
    observe(s, point, 6)
    assert s.controller.dwell.target == target, input_state(s)
    assert 0 < s.controller.dwell.progress < 1, input_state(s)
    observe(s, point, 7)


def in_modal(s, action, callback):
    errors = []
    initial = QApplication.activeModalWidget()
    called = []
    timer = QTimer()
    timer.setInterval(10)
    def run():
        dialog = QApplication.activeModalWidget()
        if dialog is None or dialog is initial:
            return
        timer.stop()
        called.append(True)
        try:
            activate_window(s, dialog)
            callback(dialog)
        except Exception as error:
            # Qt callbacks cannot propagate failures directly to pytest. Re-raise
            # them below after the modal event loop exits and cleanup completes.
            errors.append(error)
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()
    timer.timeout.connect(run)
    timer.start()
    try:
        action()
    finally:
        timer.stop()
    if errors:
        raise errors[0]
    assert called, f"Expected a modal dialog to open: {input_state(s)}"


def key(dialog, label):
    return next(button for button in dialog.findChildren(QPushButton) if button.text() == label)


@patch("services.ai_assistant_service.Client")
def test_guide_dwell_focus_physical_typing_ask_and_home(client, setup):
    client.return_value.chat.side_effect = ConnectionError("Offline test")
    s = setup
    dwell_widget(s, s.window.app_buttons[2])
    guide = s.window.steamguide_window
    dwell_widget(s, guide.question_input)
    assert QApplication.activeModalWidget() is None
    assert guide.question_input.hasFocus()
    QTest.keyClicks(QApplication.focusWidget(), "hours")
    assert guide.question_input.text() == "hours"
    dwell_widget(s, guide.ask_button)
    deadline = time.perf_counter() + 3
    while guide.ai_loader.busy and time.perf_counter() < deadline:
        QTest.qWait(5)
    assert not guide.ai_loader.busy
    assert guide.ask_button.isEnabled()
    assert "placeholder" not in guide.response_display.toPlainText()
    assert "STEAM Room Hours" in guide.source_label.text()
    dwell_widget(s, guide.home_button)
    assert s.window.isVisible()


def test_readonly_or_disabled_fields_do_not_receive_dwell_focus(setup):
    s = setup
    field = QLineEdit(s.window)
    field.show()
    field.setText("original")
    s.window.mode_button.setFocus()
    field.setReadOnly(True)
    s.controller.activate_target((field, "edit", None))
    assert not field.hasFocus()
    field.setReadOnly(False)
    field.setEnabled(False)
    s.controller.activate_target((field, "edit", None))
    assert not field.hasFocus()
    assert field.text() == "original"


def test_dropdown_selection_and_cancel_preserve_underlying_values(setup):
    s = setup
    combo = QComboBox(s.window)
    combo.addItem("First", 17)
    combo.addItem("Second", 42)
    combo.addItem("Disabled", 99)
    combo.model().item(2).setEnabled(False)
    combo.show()
    def select(dialog):
        assert isinstance(dialog, TouchChoices)
        s.app.processEvents()
        viewport = dialog.items.viewport()
        position = viewport.mapToGlobal(dialog.items.visualItemRect(dialog.items.item(1)).center())
        s.controller.use_window(dialog)
        observe(s, (position.x(), position.y()), 13)
        dwell_widget(s, dialog.select_button)
    in_modal(s, lambda: s.controller.activate_target((combo, "choice", None)), select)
    assert combo.currentData() == 42
    picker = TouchChoices(combo)
    picker.items.setCurrentRow(2)
    assert not picker.select_button.isEnabled()
    picker.reject()
    assert combo.currentData() == 42


def test_gcode_navigation_file_list_and_home(setup, tmp_path):
    s = setup
    from sage_apps import gcode_display_print_app as module
    for name in ("a.gcode", "b.gcode"):
        (tmp_path / name).write_text("G1 X0 Y0\nG1 X10 Y10\n")
    with patch.object(module, "GCODE_DIR", tmp_path), patch.object(module, "THUMB_DIR", tmp_path / "thumbs"):
        dwell_widget(s, s.window.app_buttons[1])
    viewer = s.window.gcode_window
    assert not viewer.start_print_button.isEnabled()
    dwell_widget(s, viewer.next_button)
    assert viewer.filename_label.text() == "b.gcode"
    def choose(dialog):
        items = dialog.findChild(QListWidget)
        assert items is not None
        s.app.processEvents()
        position = items.viewport().mapToGlobal(items.visualItemRect(items.item(0)).center())
        s.controller.use_window(dialog)
        observe(s, (position.x(), position.y()), 13)
        from PySide6.QtWidgets import QDialogButtonBox
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open)
        dwell_widget(s, button)
    in_modal(s, lambda: dwell_widget(s, viewer.file_list_button), choose)
    assert viewer.filename_label.text() == "a.gcode"
    dwell_widget(s, viewer.home_button)
    assert s.window.isVisible()


def test_reference_scrolling_and_close(setup):
    s = setup
    dwell_widget(s, s.window.app_buttons[2])
    guide = s.window.steamguide_window
    def read(dialog):
        viewer = dialog.findChild(QTextBrowser)
        viewer.setPlainText("\n".join(f"Instruction {i}" for i in range(300)))
        s.app.processEvents()
        before = viewer.verticalScrollBar().value()
        dwell_widget(s, key(dialog, "Down"))
        assert viewer.verticalScrollBar().value() > before
        after = viewer.verticalScrollBar().value()
        observe(s, center(key(dialog, "Down")), 20)
        assert viewer.verticalScrollBar().value() == after
        dwell_widget(s, key(dialog, "Close"))
    in_modal(s, lambda: dwell_widget(s, guide.reference_layout.itemAt(0).widget()), read)
    assert guide.isVisible()


def test_account_tabs_close_and_external_windows_are_isolated(setup):
    s = setup
    from sage_apps.account_management_app import AccountManagementDialog
    with patch.object(AccountManagementDialog, "_start_operation"):
        dialog = AccountManagementDialog(1, "boss_admin", parent=s.window)
    dialog.setModal(True)
    dialog.show()
    activate_window(s, dialog)
    bar = dialog.tabs.tabBar()
    position = bar.mapToGlobal(bar.tabRect(1).intersected(bar.rect()).center())
    s.controller.use_window(dialog)
    observe(s, (position.x(), position.y()), 13)
    assert dialog.tabs.currentIndex() == 1
    assert not dialog.delete_button.isEnabled()
    dwell_widget(s, dialog.close_button)
    assert not dialog.isVisible(), input_state(s)
    external = QDialog()
    external.show()
    activate_window(s, external)
    assert s.controller.current_window() is None, input_state(s)
    observe(s, center(s.window.app_buttons[2]), 20)
    assert s.window.steamguide_window is None
    external.close()
    external.deleteLater()


def test_dwell_activation_does_not_require_native_focus(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(QWidget, "activateWindow", lambda self: None)
    set_test_active_window(None)
    assert s.controller.current_window() is None
    dwell_widget(s, s.window.app_buttons[2])
    guide = s.window.steamguide_window
    assert guide.isVisible(), input_state(s)
    dwell_widget(s, guide.home_button)
    assert s.window.isVisible(), input_state(s)


def test_login_physical_typing_account_dialog_and_logout(setup):
    s = setup
    from login_dialog import LoginDialog, LoginWorker
    from sage_apps.account_management_app import AccountManagementDialog
    def login(dialog):
        assert isinstance(dialog, LoginDialog)
        for field, text in ((dialog.username_input, "staff"), (dialog.password_input, "example password")):
            dwell_widget(s, field)
            assert QApplication.activeModalWidget() is dialog
            assert field.hasFocus()
            QTest.keyClicks(QApplication.focusWidget(), text)
        assert dialog.password_input.echoMode() == QLineEdit.EchoMode.Password
        with patch.object(LoginWorker, "run", lambda worker: worker.completed.emit(
                ("success", (7, "Staff", "boss_admin")))):
            dwell_widget(s, dialog.login_button)
            for _ in range(50):
                QTest.qWait(10)
                if dialog._thread is None:
                    break
            assert dialog._thread is None
            assert dialog.result() == QDialog.DialogCode.Accepted
    in_modal(s, lambda: dwell_widget(s, s.window.mode_button), login)
    assert s.window.session_state.user_id == 7
    assert s.window.app_buttons[0].isEnabled()
    def manage(dialog):
        assert dialog.actor_id == 7
        assert dialog.actor_role == "boss_admin"
        dwell_widget(s, dialog.close_button)
    with patch.object(AccountManagementDialog, "_start_operation"):
        in_modal(s, lambda: dwell_widget(s, s.window.app_buttons[0]), manage)
    dwell_widget(s, s.window.mode_button)
    assert s.window.session_state.mode == "student"
    assert not s.window.app_buttons[0].isEnabled()


def test_delete_confirmation_requires_separate_selection_and_can_cancel(setup):
    s = setup
    from sage_apps.account_management_app import AccountManagementDialog
    with patch.object(AccountManagementDialog, "_start_operation") as operation:
        dialog = AccountManagementDialog(1, "boss_admin", parent=s.window)
        dialog._show_accounts([(2, "Other Staff", "other", "base_specialist", True)])
        dialog.tabs.setCurrentIndex(1)
        dialog.setModal(True)
        dialog.show()
        s.app.processEvents()
        operation.reset_mock()
        def cancel(confirmation):
            assert isinstance(confirmation, QMessageBox)
            assert s.controller.current_window() is confirmation
            operation.assert_not_called()
            dwell_widget(s, confirmation.button(QMessageBox.StandardButton.No))
        in_modal(s, lambda: dwell_widget(s, dialog.delete_button), cancel)
        operation.assert_not_called()
        dialog.close()
