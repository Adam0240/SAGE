"""Spawn real disposable workers with fake native operations; no audio/models."""

import time
from types import SimpleNamespace

import pytest

from services.speech_recognition_service import SpeechRecognitionService
from services.supervised_speech_service import SupervisedSpeechRecognitionService


def stall():
    while True:
        time.sleep(1)


class FakeModel:
    def __init__(self, stage, entered):
        self.stage = stage
        self.entered = entered
        self.calls = 0

    def transcribe(self, *args, **kwargs):
        if self.stage == "transcribe":
            self.entered.set()
            stall()
        self.calls += 1

        def segments():
            if self.stage == "segments":
                self.entered.set()
                stall()
            yield SimpleNamespace(text=f"answer {self.calls}")
        return segments(), None


class FakeEngine(SpeechRecognitionService):
    def __init__(self, stage="ok", entered=None):
        super().__init__()
        self.stage = stage
        self.entered = entered

    def _capture_audio(self):
        if self.stage == "capture":
            self.entered.set()
            stall()
        self._on_ready()
        return [1]

    def _load_model(self):
        if self.stage == "load":
            self.entered.set()
            stall()
        if self.model is None:
            self.model = FakeModel(self.stage, self.entered)


def finish(service):
    service._recording_thread.join(8)
    assert not service._recording_thread.is_alive()
    assert not service.is_recording()


@pytest.mark.parametrize("stage", ["capture", "load", "transcribe", "segments"])
@pytest.mark.parametrize("cancel", [False, True])
def test_native_stalls_terminate_before_retry_and_suppress_cancelled_callbacks(stage, cancel):
    service = SupervisedSpeechRecognitionService(
        engine_factory=FakeEngine, stage=stage, capture_timeout=3,
        transcription_timeout=0.3, cancel_grace=0.1)
    entered = service.context.Event()
    service.options["entered"] = entered
    results, errors = [], []
    try:
        assert service.start_recording(results.append, errors.append)
        assert entered.wait(5)
        assert not service.start_recording()
        if cancel:
            service.cancel_recording()
        finish(service)
        assert service._process is None
        assert results == []
        assert len(errors) == (0 if cancel else 1)
        if errors:
            assert "timed out" in errors[0]
        service.options["stage"] = "ok"
        assert service.start_recording(results.append, errors.append)
        finish(service)
        assert results == ["answer 1"]
    finally:
        service.shutdown()
        finish(service)


def test_reuses_process_and_model_and_shutdown_releases_idle_owner():
    service = SupervisedSpeechRecognitionService(engine_factory=FakeEngine)
    results, ready, captured = [], [], []
    service.on_captured = lambda: captured.append(True)
    try:
        for _ in range(2):
            assert service.start_recording(results.append, on_ready=lambda: ready.append(True))
            finish(service)
        assert results == ["answer 1", "answer 2"]
        assert ready == captured == [True, True]
    finally:
        service.shutdown()
        finish(service)
    assert service._process is None
    assert not service.start_recording()


def test_shutdown_during_blocked_capture_returns_promptly_and_reaps_worker():
    service = SupervisedSpeechRecognitionService(engine_factory=FakeEngine, stage="capture", cancel_grace=0.1)
    entered = service.context.Event()
    service.options["entered"] = entered
    received = []
    try:
        assert service.start_recording(received.append, received.append)
        assert entered.wait(5)
        before = time.monotonic()
        service.shutdown()
        assert time.monotonic() - before < 0.5
        finish(service)
        assert service._process is None
        assert received == []
    finally:
        service.shutdown()
        finish(service)


def test_unexpected_worker_exit_reports_error_and_allows_retry():
    service = SupervisedSpeechRecognitionService(engine_factory=FakeEngine, stage="capture")
    entered = service.context.Event()
    service.options["entered"] = entered
    results, errors = [], []
    try:
        assert service.start_recording(results.append, errors.append)
        assert entered.wait(5)
        service._process.terminate()
        finish(service)
        assert len(errors) == 1
        service.options["stage"] = "ok"
        assert service.start_recording(results.append, errors.append)
        finish(service)
        assert results == ["answer 1"]
    finally:
        service.shutdown()
        finish(service)
