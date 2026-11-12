
"""Run SAGE AI responses in the background without blocking Qt."""

from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import QObject, QTimer, Signal

from services.ai_assistant_service import AIAssistantService
from services.document_retrieval_service import DocumentRetrievalService
from services.guide_response_service import GuideResponse, GuideResponseService


def generate_response(question, directory, request_id, cancelled, results, shutdown):
    """Generate an answer without accessing any Qt widgets."""
    if cancelled.is_set() or shutdown.is_set():
        return
    try:
        retrieval = DocumentRetrievalService(directory)

        try:
            assistant = AIAssistantService(retrieval)
            response = assistant.respond(question)

        except Exception:
            # Preserve documentation-based answers if AI setup fails.
            result = retrieval.search(question)
            response = GuideResponseService().respond(question, result)

    except Exception:
        response = GuideResponse(
            "Reference documentation is unavailable. "
            "Please ask the STEAM Specialist for assistance."
        )

    # Ignore answers from cancelled requests.
    if not cancelled.is_set() and not shutdown.is_set():
        results.put((request_id, response))


class AIResponseLoader(QObject):
    completed = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.request_id = 0
        self.thread = None
        self.pending = None
        self.cancelled = Event()
        self.results = Queue()
        self.shutdown = Event()

        # Poll for results on the Qt interface thread.
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._poll)

        # Capture only Python state: destruction must never dereference this
        # QObject, and an unfinished worker must not keep it alive.
        self.destroyed.connect(self.shutdown.set)

    @property
    def busy(self):
        return self.thread is not None or self.pending is not None

    def submit(self, question, directory):
        # Assign each question a unique request identifier.
        self.request_id += 1
        self.cancelled.set()

        self.pending = (
            self.request_id,
            question,
            Path(directory),
        )

        self.timer.start()
        self._start_pending()

        return self.request_id

    def cancel(self):
        # Discard results without interrupting an active Ollama request.
        self.request_id += 1
        self.cancelled.set()
        self.pending = None
        # The abandoned daemon owns only Python data, so it can finish without
        # blocking a new question or the destruction of the guide.
        self.thread = None
        self.timer.stop()

    def _start_pending(self):
        if self.thread is not None or self.pending is None:
            return

        request_id, question, directory = self.pending
        self.pending = None
        self.cancelled = Event()

        self.thread = Thread(
            target=generate_response,
            args=(
                question,
                directory,
                request_id,
                self.cancelled,
                self.results,
                self.shutdown,
            ),
            daemon=True,
        )

        self.thread.start()

    def _poll(self):
        # Determine whether the previous request has finished.
        if self.thread is not None and not self.thread.is_alive():
            self.thread = None

        latest = None

        while True:
            try:
                request_id, response = self.results.get_nowait()
            except Empty:
                break

            # Accept only the latest valid request.
            if request_id == self.request_id:
                latest = (request_id, response)

        self._start_pending()

        if not self.busy:
            self.timer.stop()

        # Deliver the result to Qt on the main interface thread.
        if latest is not None:
            self.completed.emit(*latest)
