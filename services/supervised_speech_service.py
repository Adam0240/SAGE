"""Bound native speech stalls using one reusable, disposable child process."""

import multiprocessing
import threading
import time

from services.speech_recognition_service import SpeechRecognitionService


def _speech_process(connection, stop, cancel, options, engine_factory):
    engine = engine_factory(**options)
    engine._stop_event = stop
    engine._cancel_event = cancel
    engine.on_captured = lambda: connection.send(("captured", ""))
    try:
        while connection.recv() == "record":
            engine._on_ready = lambda: connection.send(("ready", ""))
            engine._record_and_transcribe(
                lambda text: connection.send(("result", text)),
                lambda error: connection.send(("error", error)),
            )
            connection.send(("done", ""))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class SupervisedSpeechRecognitionService:
    """Callbacks run on a supervisor thread; native work never runs in the GUI."""

    def __init__(self, *, capture_timeout=None, transcription_timeout=120,
                 cancel_grace=1, engine_factory=SpeechRecognitionService, **options):
        self.options = options
        self.capture_timeout = capture_timeout or options.get("max_recording_duration", 20) + 10
        self.transcription_timeout = transcription_timeout
        self.cancel_grace = cancel_grace
        self.engine_factory = engine_factory
        self.context = multiprocessing.get_context("spawn")
        self._process = None
        self._connection = None
        self._stop = None
        self._cancel = None
        self._cancel_requested = threading.Event()
        self._shutdown = threading.Event()
        self._lock = threading.Lock()
        self._is_recording = False
        self._recording_thread = None
        self.on_captured = lambda: None

    def is_recording(self):
        with self._lock:
            return self._is_recording

    def start_recording(self, on_result=None, on_error=None, on_ready=None):
        with self._lock:
            if self._is_recording or self._shutdown.is_set():
                return False
            self._is_recording = True
            self._cancel_requested.clear()
            self._stop_requested = False
            try:
                self._recording_thread = threading.Thread(
                    target=self._run, args=(on_result, on_error, on_ready, self.on_captured),
                    daemon=True)
                self._recording_thread.start()
            except Exception:
                self._is_recording = False
                raise
        return True

    def stop_recording(self):
        # Also remember a stop requested before process startup finishes.
        self._stop_requested = True
        if self._stop is not None:
            self._stop.set()

    def cancel_recording(self):
        self._cancel_requested.set()
        if self._cancel is not None:
            self._cancel.set()
        if self._stop is not None:
            self._stop.set()

    def shutdown(self):
        self._shutdown.set()
        self.cancel_recording()
        with self._lock:
            if not self._is_recording:
                self._is_recording = True
                self._recording_thread = threading.Thread(target=self._close_idle, daemon=True)
                self._recording_thread.start()

    def _close_idle(self):
        try:
            self._dispose()
        finally:
            with self._lock:
                self._is_recording = False

    def _dispose(self):
        process = self._process
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
            if process.is_alive():
                # Never permit another microphone owner if termination failed.
                self._shutdown.set()
                raise RuntimeError("Speech worker could not stop. Restart SAGE before using voice.")
            process.close()
            self._process = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _ensure_process(self):
        if self._process is not None and not self._process.is_alive():
            self._dispose()
        if self._process is None:
            self._connection, child = self.context.Pipe()
            self._stop, self._cancel = self.context.Event(), self.context.Event()
            process = self.context.Process(target=_speech_process, args=(
                child, self._stop, self._cancel, self.options, self.engine_factory), daemon=True)
            try:
                process.start()
            finally:
                child.close()
            self._process = process

    def _run(self, on_result, on_error, on_ready, on_captured):
        outcome = None
        try:
            self._ensure_process()
            self._stop.clear()
            self._cancel.clear()
            if self._stop_requested:
                self._stop.set()
            self._connection.send("record")
            deadline = time.monotonic() + self.capture_timeout
            cancellation_deadline = None
            while True:
                now = time.monotonic()
                if self._cancel_requested.is_set():
                    self._cancel.set()
                    self._stop.set()
                    if cancellation_deadline is None:
                        cancellation_deadline = now + self.cancel_grace
                    if now >= cancellation_deadline:
                        self._dispose()
                        break
                if now >= deadline:
                    self._dispose()
                    raise TimeoutError("Speech timed out. The worker was stopped; please try again.")
                if self._connection.poll(0.05):
                    kind, value = self._connection.recv()
                    if kind == "done":
                        break
                    if kind == "captured":
                        deadline = time.monotonic() + self.transcription_timeout
                    if not self._cancel_requested.is_set():
                        if kind == "ready" and on_ready:
                            on_ready()
                        elif kind == "captured":
                            on_captured()
                        elif kind in ("result", "error"):
                            outcome = (kind, value)
                elif not self._process.is_alive():
                    raise RuntimeError("Speech worker stopped unexpectedly. Please try again.")
        except Exception as error:
            outcome = ("error", str(error) or "Speech worker stopped unexpectedly. Please try again.")
            try:
                self._dispose()
            except Exception as cleanup_error:
                outcome = ("error", str(cleanup_error))
        finally:
            try:
                if self._shutdown.is_set():
                    try:
                        self._dispose()
                    except Exception as cleanup_error:
                        outcome = ("error", str(cleanup_error))
                if outcome is not None and not self._cancel_requested.is_set():
                    callback = on_result if outcome[0] == "result" else on_error
                    if callback:
                        try:
                            callback(outcome[1])
                        except Exception as error:
                            if outcome[0] == "result" and on_error:
                                on_error(str(error))
            finally:
                with self._lock:
                    self._is_recording = False
