"""Map camera observations to the existing Home buttons, without OS mouse input."""

from contextlib import contextmanager
import time

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from TouchControls.calibration import Calibration, DEFAULT_CALIBRATION_PATH
from TouchControls.camera_manager import DEFAULT_MODEL_PATH
from TouchControls.camera_worker import CameraWorker
from TouchControls.dwell import DwellTracker


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
        self.last_timestamp = 0
        self.accept_after = time.monotonic()
        self.filtered = None
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.check_idle)
        home.installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def geometry(self):
        screen = self.home.screen()
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
            self.stopped.emit()
            return
        self.worker = self.worker_factory(self.calibration.camera_index, DEFAULT_MODEL_PATH, self)
        self.worker.observation.connect(self.on_observation)
        self.worker.failed.connect(self.fail)
        self.worker.finished.connect(self.on_finished)
        self.enabled = True
        self.reset()
        self.status_changed.emit("Starting camera…")
        self.timer.start()
        self.worker.start()

    def reset(self):
        self.accept_after = time.monotonic()
        self.dwell.reset()
        self.clear_pointer()

    def clear_pointer(self):
        self.filtered = None
        self.overlay.point = None
        self.overlay.hide()
        self.dwell.cancel()

    def active(self):
        return (self.enabled and not self.pause_depth and self.home.isVisible()
                and QApplication.activeWindow() is self.home
                and QApplication.activeModalWidget() is None
                and QApplication.activePopupWidget() is None)

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
        if event.type() in (QEvent.Type.Hide, QEvent.Type.Show, QEvent.Type.WindowDeactivate,
                            QEvent.Type.WindowActivate, QEvent.Type.Move, QEvent.Type.Resize):
            self.reset()
        return False

    def check_idle(self):
        if not self.active():
            self.reset()
        elif time.monotonic() - self.last_timestamp > 0.3:
            self.clear_pointer()
            self.status_changed.emit("Camera enabled — waiting for your index finger.")

    def target_at(self, point):
        for button in [self.home.mode_button, *self.home.app_buttons, self.home.camera_button]:
            if not button.isVisible() or not button.isEnabled():
                continue
            origin = button.mapTo(self.home, QPoint(0, 0))
            x, y = point[0] - origin.x(), point[1] - origin.y()
            if not (0 <= x < button.width() and 0 <= y < button.height()):
                continue
            if button in self.home.app_buttons:
                if (x - button.width() / 2) ** 2 + (y - button.height() / 2) ** 2 > (button.width() / 2) ** 2:
                    continue
            return button
        return None

    def on_observation(self, tip, size, timestamp):
        now = time.monotonic()
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
        origin = self.home.mapToGlobal(QPoint(0, 0))
        raw = (mapped[0] + geometry[0] - origin.x(), mapped[1] + geometry[1] - origin.y())
        if not (0 <= raw[0] < self.home.width() and 0 <= raw[1] < self.home.height()):
            self.dwell.observe(None, timestamp)
            self.clear_pointer()
            return
        self.filtered = raw if self.filtered is None else tuple(
            previous + 0.4 * (current - previous) for previous, current in zip(self.filtered, raw))
        # Hit-test raw coordinates so smoothing cannot prolong a dwell after departure.
        target = self.target_at(raw)
        activate = self.dwell.observe(target, timestamp)
        self.overlay.setGeometry(self.home.rect())
        self.overlay.point = self.filtered
        self.overlay.progress = self.dwell.progress
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.update()
        self.status_changed.emit("Hold over a button for one second. Move away before selecting it again.")
        if activate and self.active() and target.isEnabled():
            target.click()

    def stop(self):
        self.enabled = False
        self.timer.stop()
        self.reset()
        if self.worker is not None:
            self.worker.requestInterruption()

    def fail(self, message):
        self.stop()
        self.status_changed.emit(f"Camera controls stopped: {message}")

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
