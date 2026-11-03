"""Qt supervisor for an isolated camera process, with bounded shutdown."""

import multiprocessing
import time

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot


def capture_process(connection, camera_index, model_path):
    try:
        # The child alone owns native capture and tracking resources.
        from TouchControls.camera_manager import CameraManager

        with CameraManager(camera_index, model_path) as camera:
            while not connection.poll():
                if not camera.update():
                    connection.send(("error", camera.last_error))
                    return
                height, width = camera.frame.shape[:2]
                connection.send(("observation", camera.index_fingertip,
                                 (width, height), time.monotonic()))
                if connection.poll(0.02):
                    return
    except Exception as error:
        try:
            connection.send(("error", str(error)))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class CameraWorker(QObject):
    """Keep existing worker signals without putting capture in a QThread.

    Only small observations cross the pipe, never frames. A bounded drain keeps
    a fast child from monopolizing the GUI event loop.
    """

    observation = Signal(object, object, float)
    failed = Signal(str)
    finished = Signal()
    _observation_ready = Signal(object)

    def __init__(self, camera_index, model_path, parent=None, *,
                 process_target=capture_process, startup_timeout=30.0,
                 frame_timeout=5.0, stop_timeout=0.75):
        super().__init__(parent)
        self.camera_index = camera_index
        self.model_path = str(model_path)
        self.process_target = process_target
        self.startup_timeout = startup_timeout
        self.frame_timeout = frame_timeout
        self.stop_timeout = stop_timeout
        self.process = None
        self.connection = None
        self.deadline = 0
        self.stop_deadline = None
        self.terminated = False
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._poll)
        self._observation_ready.connect(self._deliver_observation,
                                        Qt.ConnectionType.QueuedConnection)

    def start(self):
        if self.process is not None:
            return
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=self.process_target,
            args=(child, self.camera_index, self.model_path), daemon=True)
        self.stop_deadline = None
        self.terminated = False
        try:
            self.process.start()
        except Exception as error:
            self.process.close()
            self.process = None
            self.connection.close()
            self.connection = None
            self.failed.emit(f"Unable to start camera tracking: {error}")
            self.finished.emit()
            return
        finally:
            child.close()
        self.deadline = time.monotonic() + self.startup_timeout
        self.timer.start()

    def isRunning(self):
        return self.process is not None

    def requestInterruption(self):
        if self.process is None or self.stop_deadline is not None:
            return
        self.stop_deadline = time.monotonic() + self.stop_timeout
        try:
            self.connection.send("stop")
        except (OSError, EOFError):
            pass

    def _fail(self, message):
        if self.stop_deadline is None:
            self.requestInterruption()
            self.failed.emit(message)

    def _poll(self):
        if self.process is None:
            return
        latest = None
        try:
            for _ in range(32):
                if not self.connection.poll():
                    break
                message = self.connection.recv()
                if self.stop_deadline is not None:
                    continue
                if message[0] == "error":
                    self._fail(message[1])
                elif message[0] == "observation":
                    self.deadline = time.monotonic() + self.frame_timeout
                    latest = message[1:]
        except (EOFError, OSError):
            pass
        if not self.process.is_alive():
            if self.stop_deadline is None:
                self._fail("Camera tracking process stopped unexpectedly.")
            self._finish()
            return
        now = time.monotonic()
        if self.stop_deadline is None and now >= self.deadline:
            self._fail("Camera tracking timed out. Check the camera connection and restart.")
        if self.stop_deadline is not None and now >= self.stop_deadline:
            if not self.terminated:
                self.process.terminate()
                self.terminated = True
            else:
                self.process.kill()
            self.stop_deadline = now + 0.5
        if latest is not None and self.stop_deadline is None:
            # Deliver outside the timer callback: Qt does not reenter that timer
            # while a dwell handler's modal exec() is still on its call stack.
            self._observation_ready.emit(latest)

    @Slot(object)
    def _deliver_observation(self, observation):
        if self.process is not None and self.stop_deadline is None:
            self.observation.emit(*observation)

    def _finish(self):
        self.timer.stop()
        self.process.join(timeout=0)
        self.process.close()
        self.process = None
        self.connection.close()
        self.connection = None
        self.finished.emit()

    def wait(self):
        """Bounded fallback for application quit, when Qt timers cannot run.

        Normal window closure is asynchronous through requestInterruption().
        This fallback waits at most the grace period plus two half-second joins.
        """
        if self.process is None:
            return True
        self.requestInterruption()
        self.process.join(timeout=self.stop_timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=0.5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=0.5)
        if not self.process.is_alive():
            self._finish()
            return True
        return False
