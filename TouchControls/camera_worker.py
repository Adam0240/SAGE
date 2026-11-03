"""Shared worker for calibration and camera input; owns the camera on its thread."""

import time
from PySide6.QtCore import QThread, Signal
from TouchControls.camera_manager import CameraManager


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
