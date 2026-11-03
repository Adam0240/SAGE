"""Standalone four-point calibration with five independent accuracy checks."""

import argparse
from collections import deque
import math
from pathlib import Path
import sys
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from TouchControls.camera_manager import CameraManager, DEFAULT_MODEL_PATH
from TouchControls.calibration import (
    Calibration, DEFAULT_CALIBRATION_PATH, check_points, fit_mapping, project, target_points,
)


class CameraWorker(QThread):
    observation = Signal(object, object, float)
    failed = Signal(str)

    def __init__(self, camera_index, model_path, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.model_path = model_path

    def run(self):
        try:
            with CameraManager(self.camera_index, self.model_path) as camera:
                while not self.isInterruptionRequested():
                    if not camera.update():
                        self.failed.emit(camera.last_error)
                        return
                    height, width = camera.frame.shape[:2]
                    self.observation.emit(camera.index_fingertip, (width, height), time.monotonic())
                    self.msleep(20)
        except Exception as error:
            self.failed.emit(str(error))


class CalibrationWindow(QWidget):
    def __init__(self, camera_index=0, model_path=DEFAULT_MODEL_PATH,
                 output=DEFAULT_CALIBRATION_PATH, *, start_camera=True):
        super().__init__()
        self.setWindowTitle("SAGE Hand Calibration")
        screen = QApplication.primaryScreen()
        geometry = screen.geometry()
        self.display_geometry = (geometry.x(), geometry.y(), geometry.width(), geometry.height())
        self.pixel_ratio = screen.devicePixelRatio()
        self.setGeometry(geometry)
        self.camera_index = camera_index
        self.output = Path(output)
        self.camera_size = None
        self.samples = deque(maxlen=15)
        self.last_observed = 0.0
        self.tip = None
        self.closing = False
        self.fatal_error = False
        self.worker = None
        self.restart()
        self.repaint_timer = QTimer(self)
        self.repaint_timer.timeout.connect(self.update)
        self.repaint_timer.start(100)
        if start_camera:
            self.worker = CameraWorker(camera_index, model_path, self)
            self.worker.observation.connect(self.on_observation)
            self.worker.failed.connect(self.on_failure)
            self.worker.finished.connect(self.on_worker_finished)
            self.worker.start()

    def restart(self):
        self.points = []
        self.errors = []
        self.matrix = None
        self.stage = "capture"
        self.samples.clear()
        self.accept_after = time.monotonic()
        self.message = "Place your index fingertip on the target; hold steady, then press Enter."
        self.update()

    def on_failure(self, message):
        self.fatal_error = True
        self.tip = None
        self.samples.clear()
        self.message = message + " — Press Esc, then restart after checking the camera."
        self.update()

    def on_observation(self, tip, size, timestamp):
        if self.fatal_error or self.closing or timestamp <= self.accept_after:
            return
        if self.camera_size is not None and self.camera_size != size:
            self.on_failure("Camera resolution changed during calibration.")
            return
        self.camera_size = size
        self.last_observed = timestamp
        self.tip = tip
        if tip is None or time.monotonic() - timestamp > 0.3:
            self.samples.clear()
            self.tip = None
        else:
            if self.samples and timestamp - self.samples[-1][0] > 0.3:
                self.samples.clear()
            self.samples.append((timestamp, tip))
        self.update()

    def stable_point(self):
        if (len(self.samples) < 10 or time.monotonic() - self.last_observed > 0.3
                or self.samples[-1][0] - self.samples[0][0] < 0.3):
            raise ValueError("Hold your fingertip steady on the target for about one second, then press Enter.")
        positions = np.asarray([point for _, point in self.samples])
        center = positions.mean(axis=0)
        if np.max(np.linalg.norm(positions - center, axis=1)) > 8:
            raise ValueError("Your fingertip moved too much. Hold steady and press Enter again.")
        return center.tolist()

    def current_target(self):
        width, height = self.display_geometry[2:]
        if self.stage == "capture":
            return target_points(width, height)[len(self.points)]
        if self.stage == "verify":
            return check_points(width, height)[len(self.errors)]
        return None

    def capture(self):
        if self.stage not in ("capture", "verify") or self.fatal_error:
            return
        try:
            point = self.stable_point()
            if self.stage == "capture":
                candidate = self.points + [point]
                if len(candidate) == 4:
                    self.matrix = fit_mapping(candidate, target_points(*self.display_geometry[2:]))
                    self.stage = "verify"
                self.points = candidate
                self.message = "Point captured. Move to the next target, hold steady, then press Enter."
            else:
                mapped = project(self.matrix, point)
                error = math.dist(mapped, self.current_target())
                if error > 25:
                    self.message = (f"Alignment error: {error:.0f} pixels (maximum 25). "
                                    "Reposition and retry Enter, or press R to recalibrate.")
                    self.samples.clear()
                    self.accept_after = time.monotonic()
                    self.update()
                    return
                self.errors.append(error)
                self.message = f"Check passed: {error:.1f} pixels. Move to the next target."
                if len(self.errors) == 5:
                    self.stage = "ready"
                    self.message = "All checks passed. Move your finger to inspect the green pointer. Press S to save."
            self.samples.clear()
            self.accept_after = time.monotonic()
        except ValueError as error:
            self.message = str(error)
        self.update()

    def save(self):
        if self.stage != "ready" or self.fatal_error:
            return
        try:
            screen = self.screen()
            rect = screen.geometry()
            if ((rect.x(), rect.y(), rect.width(), rect.height()) != self.display_geometry
                    or screen.devicePixelRatio() != self.pixel_ratio):
                raise ValueError("Display settings changed. Restart calibration before saving.")
            Calibration(self.camera_index, self.camera_size, self.display_geometry,
                        self.pixel_ratio, self.matrix.tolist(), self.points, self.errors).save(self.output)
            self.stage = "saved"
            self.message = f"Calibration saved to {self.output}. Press Esc to close."
        except (OSError, ValueError) as error:
            self.message = f"Could not save calibration: {error}"
        self.update()

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif not self.fatal_error and not self.closing:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.capture()
            elif event.key() == Qt.Key.Key_R:
                self.restart()
            elif event.key() == Qt.Key.Key_S:
                self.save()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("black"))
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 16))
        progress = (f"Calibration target {len(self.points) + 1}/4" if self.stage == "capture"
                    else f"Accuracy check {len(self.errors) + 1}/5" if self.stage == "verify"
                    else "Calibration complete")
        painter.drawText(QRectF(40, self.height() * 0.2, self.width() - 80, self.height() * 0.25),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         f"{progress}\n\n{self.message}\n\nEnter: capture    R: restart    Esc: cancel/close")
        tracking = "Finger detected" if self.tip is not None and time.monotonic() - self.last_observed <= 0.3 else "No fingertip detected"
        painter.drawText(QRectF(40, self.height() * 0.65, self.width() - 80, 40),
                         Qt.AlignmentFlag.AlignCenter, tracking)
        target = self.current_target()
        if target:
            painter.setPen(QPen(QColor("red"), 3))
            painter.drawEllipse(QPointF(*target), 18, 18)
            painter.drawLine(QPointF(target[0] - 25, target[1]), QPointF(target[0] + 25, target[1]))
            painter.drawLine(QPointF(target[0], target[1] - 25), QPointF(target[0], target[1] + 25))
        if self.matrix is not None and self.tip is not None and time.monotonic() - self.last_observed <= 0.3:
            try:
                mapped = project(self.matrix, self.tip)
                if 0 <= mapped[0] < self.width() and 0 <= mapped[1] < self.height():
                    painter.setPen(QPen(QColor("lime"), 3))
                    painter.drawEllipse(QPointF(*mapped), 10, 10)
            except ValueError:
                pass

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.closing = True
            self.tip = None
            self.message = "Closing camera…"
            self.worker.requestInterruption()
            self.update()
            event.ignore()
        else:
            event.accept()

    def on_worker_finished(self):
        if self.closing:
            self.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calibrate camera fingertip coordinates to the duplicated display.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_CALIBRATION_PATH)
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    window = CalibrationWindow(args.camera, args.model, args.output)
    window.showFullScreen()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
