"""One background preview at a time, retaining only the latest queued request."""

from queue import Queue, Empty
from threading import Event, Thread

from PySide6.QtCore import QObject, QTimer, Signal

from services.gcode_preview_service import (
    UnreadableGcodeError, NoPreviewableMovementError, GcodeTooLargeError, PreviewCancelled,
)


def render_preview(service, path, request, cancelled, results):
    # This function holds no widgets or Qt worker objects. QImage painting is
    # local to the worker; QPixmap creation belongs to the GUI result handler.
    try:
        result = service.get_preview(path, cancel_event=cancelled)
    except PreviewCancelled:
        result = None
    except UnreadableGcodeError:
        result = "Unable to read this G-code file."
    except NoPreviewableMovementError:
        result = "No previewable movement found."
    except GcodeTooLargeError:
        result = "This G-code file is too large to preview."
    except Exception:
        result = "Unable to generate this G-code preview."
    if not cancelled.is_set():
        results.put((request, result))


class PreviewLoader(QObject):
    completed = Signal(int, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.request = 0
        self.pending = None
        self.thread = None
        self.cancelled = Event()
        self.results = Queue()
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._poll)
        # Destruction must cancel without waiting on filesystem I/O. The worker
        # is a daemon and owns only its inputs, cancellation flag, and queue.
        self.destroyed.connect(lambda: self.cancelled.set())

    @property
    def busy(self):
        return self.thread is not None or self.pending is not None

    def submit(self, service, path):
        self.request += 1
        self.cancelled.set()
        self.pending = (self.request, service, path)
        self.timer.start()
        self._start_pending()
        return self.request

    def cancel(self):
        self.request += 1
        self.cancelled.set()
        self.pending = None

    def _start_pending(self):
        if self.thread is not None or self.pending is None:
            return
        request, service, path = self.pending
        self.pending = None
        self.cancelled = Event()
        self.thread = Thread(target=render_preview,
            args=(service, path, request, self.cancelled, self.results), daemon=True)
        self.thread.start()

    def _poll(self):
        if self.thread is not None and not self.thread.is_alive():
            self.thread = None
        latest = None
        while True:
            try:
                request, result = self.results.get_nowait()
            except Empty:
                break
            if request == self.request:
                latest = (request, result)
        self._start_pending()
        if not self.busy:
            self.timer.stop()
        if latest is not None:
            self.completed.emit(*latest)
