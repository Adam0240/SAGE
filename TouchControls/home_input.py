"""Shared camera input for SAGE's registered windows and owned dialogs."""

from contextlib import contextmanager
import time

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QPersistentModelIndex, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QWidget, QAbstractButton, QLineEdit, QComboBox, QTabBar, QListWidget, QDialog,
)
from shiboken6 import isValid

from TouchControls.calibration import Calibration, DEFAULT_CALIBRATION_PATH
from TouchControls.paths import DEFAULT_MODEL_PATH
from TouchControls.camera_worker import CameraWorker
from TouchControls.dwell import DwellTracker
from TouchControls.widgets import TouchChoices


class PointerOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self.point = None
        self.progress = 0
        self.hide()

    def paintEvent(self, event):
        if self.point is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(QPointF(*self.point), 10, 10)
        if self.progress:
            painter.setPen(QPen(QColor("#00ff88"), 4))
            x, y = self.point
            painter.drawArc(QRectF(x - 17, y - 17, 34, 34), 90 * 16, -int(self.progress * 360 * 16))


class HomeInputController(QObject):
    status_changed = Signal(str)
    error_occurred = Signal(str)
    stopped = Signal()

    def __init__(self, home, *, calibration_path=DEFAULT_CALIBRATION_PATH,
                 worker_factory=CameraWorker):
        super().__init__(home)
        self.home = home
        self.calibration_path = calibration_path
        self.worker_factory = worker_factory
        self.worker = None
        self.enabled = False
        self.pause_depth = 0
        self.calibration = None
        self.dwell = DwellTracker()
        self.overlay = PointerOverlay(home)
        self.surface = None
        self.last_timestamp = 0
        self.accept_after = time.monotonic()
        self.filtered = None
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.check_idle)
        QApplication.instance().installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def geometry(self):
        screen = (self.surface or self.home).screen()
        rect = screen.geometry()
        return (rect.x(), rect.y(), rect.width(), rect.height()), screen.devicePixelRatio()

    def start(self):
        if self.worker is not None:
            return
        try:
            self.calibration = Calibration.load(self.calibration_path)
            geometry, ratio = self.geometry()
            if not self.calibration.matches_setup(self.calibration.camera_index,
                    self.calibration.camera_size, geometry, ratio):
                raise ValueError("Display settings changed. Run hand calibration again.")
        except (OSError, ValueError) as error:
            self.status_changed.emit(f"Camera controls unavailable: {error}")
            self.error_occurred.emit(str(error))
            self.stopped.emit()
            return
        self.worker = self.worker_factory(self.calibration.camera_index, DEFAULT_MODEL_PATH, self)
        self.worker.observation.connect(self.on_observation)
        self.worker.failed.connect(self.fail)
        self.worker.finished.connect(self.on_finished)
        self.enabled = True
        self.reset()
        self.use_window(self.current_window())
        self.status_changed.emit("Starting camera…")
        self.timer.start()
        self.worker.start()

    def reset(self):
        self.accept_after = time.monotonic()
        self.dwell.reset()
        self.clear_pointer()

    def clear_pointer(self):
        self.filtered = None
        if isValid(self.overlay):
            self.overlay.point = None
            self.overlay.hide()
        self.dwell.cancel()

    def owns(self, widget):
        while widget is not None:
            if widget is self.home:
                return True
            widget = widget.parentWidget()
        return False

    def current_window(self):
        active = QApplication.activeWindow()
        if active is None or not self.owns(active) or QApplication.activePopupWidget() is not None:
            return None
        window = QApplication.activeModalWidget() or active
        if (window.isVisible() and self.owns(window)
                and (window is self.home or isinstance(window, QDialog)
                     or window.property("sageTouchWindow"))):
            return window
        return None

    def active(self):
        return self.enabled and not self.pause_depth and self.current_window() is not None

    def use_window(self, window):
        if self.surface is window and isValid(self.overlay):
            return
        self.reset()
        self.surface = window
        if window is not None:
            self.prepare_window(window)
        if not isValid(self.overlay):
            self.overlay = PointerOverlay(self.home)
        self.overlay.setParent(window or self.home)
        self.overlay.hide()

    def prepare_window(self, window):
        if window.property("touchPrepared"):
            return
        window.setProperty("touchPrepared", True)
        for control in window.findChildren(QWidget):
            if control.window() is not window:
                continue
            if isinstance(control, (QAbstractButton, QLineEdit, QComboBox)):
                control.setMinimumHeight(max(44, control.minimumHeight()))
            if isinstance(control, QTabBar):
                control.currentChanged.connect(self.reset)
            if isinstance(control, QListWidget):
                control.model().modelReset.connect(self.reset)
                control.model().rowsRemoved.connect(self.reset)

    @contextmanager
    def suspended(self):
        self.pause_depth += 1
        self.reset()
        try:
            yield
        finally:
            self.pause_depth -= 1
            self.reset()

    def eventFilter(self, watched, event):
        if isinstance(watched, QWidget) and watched.isWindow() and self.owns(watched):
            if event.type() == QEvent.Type.Show:
                self.prepare_window(watched)
            if event.type() in (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.WindowDeactivate,
                                QEvent.Type.WindowActivate, QEvent.Type.Move, QEvent.Type.Resize):
                self.reset()
            if event.type() == QEvent.Type.Hide and watched is self.surface:
                self.use_window(None)
        return False

    def check_idle(self):
        self.use_window(self.current_window() if self.enabled else None)
        if not self.active():
            self.reset()
        elif time.monotonic() - self.last_timestamp > 0.3:
            self.clear_pointer()
            self.status_changed.emit("Camera enabled — waiting for your index finger.")

    def target_at(self, point):
        surface = self.surface or self.current_window()
        if surface is None:
            return None
        child = surface.childAt(QPoint(int(point[0]), int(point[1])))
        while child is not None and child is not surface:
            if not child.isEnabled():
                return None
            local = child.mapFrom(surface, QPoint(int(point[0]), int(point[1])))
            if isinstance(child, QLineEdit):
                if child.isReadOnly():
                    return None
                return (child, "edit", None)
            if isinstance(child, QComboBox):
                return (child, "choice", None)
            if isinstance(child, QAbstractButton):
                if child in self.home.app_buttons:
                    if (local.x() - child.width()/2)**2 + (local.y() - child.height()/2)**2 > (child.width()/2)**2:
                        return None
                return (child, "button", None)
            if isinstance(child, QTabBar):
                index = child.tabAt(local)
                if index >= 0 and child.isTabEnabled(index) and index != child.currentIndex():
                    return (child, "tab", index)
                return None
            if isinstance(child, QListWidget):
                index = child.indexAt(child.viewport().mapFrom(surface, QPoint(int(point[0]), int(point[1]))))
                if index.isValid() and index.flags() & Qt.ItemFlag.ItemIsEnabled and index.flags() & Qt.ItemFlag.ItemIsSelectable:
                    return (child, "item", QPersistentModelIndex(index))
                return None
            child = child.parentWidget()
        return None

    def activate_target(self, target):
        control, kind, index = target
        if not isValid(control) or not control.isVisible() or not control.isEnabled():
            return
        if control.window() is not self.current_window():
            return
        if kind == "button":
            control.click()
        elif kind == "tab":
            if control.isTabEnabled(index):
                control.setCurrentIndex(index)
        elif kind == "item":
            if (index.isValid() and index.flags() & Qt.ItemFlag.ItemIsEnabled
                    and index.flags() & Qt.ItemFlag.ItemIsSelectable):
                control.setCurrentRow(index.row())
        elif kind == "edit":
            if not control.isReadOnly():
                control.setFocus(Qt.FocusReason.OtherFocusReason)
        elif kind == "choice":
            self.reset()
            dialog = TouchChoices(control)
            if dialog.exec() == QDialog.DialogCode.Accepted and control.isEnabled():
                row = dialog.items.currentRow()
                model_index = control.model().index(row, control.modelColumn(), control.rootModelIndex())
                if model_index.isValid() and model_index.flags() & Qt.ItemFlag.ItemIsEnabled:
                    control.setCurrentIndex(row)
            dialog.deleteLater()
            self.reset()

    def on_observation(self, tip, size, timestamp):
        now = time.monotonic()
        self.use_window(self.current_window() if self.enabled else None)
        if not self.enabled or timestamp <= self.accept_after or timestamp <= self.last_timestamp:
            return
        if not self.active():
            self.reset()
            return
        if now - timestamp > 0.3 or timestamp > now:
            self.clear_pointer()
            return
        geometry, ratio = self.geometry()
        if not self.calibration.matches_setup(self.calibration.camera_index, size, geometry, ratio):
            self.fail("Camera resolution or display settings changed. Run hand calibration again.")
            return
        if timestamp - self.last_timestamp > 0.3:
            self.clear_pointer()
        self.last_timestamp = timestamp
        if tip is None:
            self.clear_pointer()
            self.status_changed.emit("Camera enabled — waiting for your index finger.")
            return
        try:
            mapped = self.calibration.map_point(tip)
        except ValueError:
            mapped = None
        if mapped is None:
            self.dwell.observe(None, timestamp)
            self.clear_pointer()
            return
        origin = self.surface.mapToGlobal(QPoint(0, 0))
        raw = (mapped[0] + geometry[0] - origin.x(), mapped[1] + geometry[1] - origin.y())
        if not (0 <= raw[0] < self.surface.width() and 0 <= raw[1] < self.surface.height()):
            self.dwell.observe(None, timestamp)
            self.clear_pointer()
            return
        self.filtered = raw if self.filtered is None else tuple(
            previous + 0.4 * (current - previous) for previous, current in zip(self.filtered, raw))
        # Hit-test raw coordinates so smoothing cannot prolong a dwell after departure.
        target = self.target_at(raw)
        activate = self.dwell.observe(target, timestamp)
        self.overlay.setGeometry(self.surface.rect())
        self.overlay.point = self.filtered
        self.overlay.progress = self.dwell.progress
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.update()
        self.status_changed.emit("Hold over a button for one second. Move away before selecting it again.")
        if activate and self.active():
            self.activate_target(target)

    def stop(self):
        self.enabled = False
        self.timer.stop()
        self.reset()
        if self.worker is not None:
            self.worker.requestInterruption()

    def fail(self, message):
        self.stop()
        self.status_changed.emit(f"Camera controls stopped: {message}")
        self.error_occurred.emit(message)

    def on_finished(self):
        self.stop()
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.stopped.emit()

    def shutdown(self):
        self.stop()
        if self.worker is not None:
            self.worker.wait()
