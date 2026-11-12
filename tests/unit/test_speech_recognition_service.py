"""Speech lifecycle tests: no microphone, model, network, or Qt required."""

from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from services import speech_recognition_service as speech


class FakeStream:
    def __init__(self, read):
        self.read = read
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


def block(volume=0.1):
    return np.full((1600, 1), volume, dtype=np.float32)


@pytest.fixture
def harness():
    model = Mock()
    model.transcribe.return_value = (
        [SimpleNamespace(text=" Hello "), SimpleNamespace(text=" SAGE. ")], None,
    )
    factory = Mock(return_value=model)
    stream_factory = Mock()
    service = speech.SpeechRecognitionService(
        model_factory=factory, stream_factory=stream_factory,
    )
    results, errors = [], []
    yield SimpleNamespace(service=service, model=model, factory=factory,
                          stream_factory=stream_factory, results=results, errors=errors)
    service.cancel_recording()
    if service._recording_thread is not None:
        service._recording_thread.join(3)
        assert not service._recording_thread.is_alive()


def finish(h):
    h.service._recording_thread.join(3)
    assert not h.service._recording_thread.is_alive(), "worker did not finish"
    assert not h.service.is_recording()


def start(h):
    assert h.service.start_recording(h.results.append, h.errors.append)


@pytest.mark.parametrize("volume,expected", [(0.1, ["Hello SAGE."]), (0, [""])])
def test_manual_stop_closes_stream_and_transcribes_only_speech(harness, volume, expected):
    h = harness
    entered, release = Event(), Event()

    def read(size):
        assert size == 1600
        entered.set()
        assert release.wait(3)
        return block(volume), False

    stream = FakeStream(read)
    h.stream_factory.return_value = stream
    start(h)
    try:
        assert entered.wait(3)
        assert h.service.is_recording()
        assert not h.service.start_recording()
        h.service.stop_recording()
    finally:
        release.set()
    finish(h)
    assert stream.closed
    assert h.results == expected
    assert h.errors == []
    h.stream_factory.assert_called_once_with(samplerate=16000, channels=1, dtype="float32")
    if volume:
        h.factory.assert_called_once_with("base.en", device="cpu", compute_type="int8",
                                          local_files_only=True)
        args, kwargs = h.model.transcribe.call_args
        np.testing.assert_array_equal(args[0], block().flatten())
        assert kwargs == {"language": "en", "beam_size": 5}
    else:
        h.factory.assert_not_called()


@pytest.mark.parametrize("stage", ["capture", "load", "transcribe", "segments"])
@pytest.mark.parametrize("fail", [False, True])
def test_cancel_suppresses_late_results_and_errors(harness, monkeypatch, stage, fail):
    h = harness
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(3)
        if fail:
            raise RuntimeError("late failure")

    def capture():
        if stage == "capture":
            pause()
        return block().flatten()

    def load(*args, **kwargs):
        if stage == "load":
            pause()
        return h.model

    def segments():
        if stage == "segments":
            pause()
        yield SimpleNamespace(text="late answer")

    def transcribe(*args, **kwargs):
        if stage == "transcribe":
            pause()
        return segments(), None

    monkeypatch.setattr(h.service, "_capture_audio", capture)
    h.factory.side_effect = load
    h.model.transcribe.side_effect = transcribe
    start(h)
    try:
        assert entered.wait(3)
        h.service.cancel_recording()
        h.service.cancel_recording()
        assert h.service.is_recording()
        assert not h.service.start_recording()
    finally:
        release.set()
    finish(h)
    assert h.results == h.errors == []
    # A subsequent request clears cancellation and can succeed.
    start(h)
    finish(h)
    assert h.results == ([] if fail else ["late answer"])
    assert h.errors == (["late failure"] if fail else [])


@pytest.mark.parametrize("kind", ["open", "read", "overflow", "load", "transcribe", "segments"])
def test_errors_report_once_release_resources_and_allow_retry(harness, kind):
    h = harness

    def read(size):
        h.service.stop_recording()
        if kind == "read":
            raise RuntimeError("read failed")
        return block(), kind == "overflow"

    stream = FakeStream(read)
    h.stream_factory.return_value = stream
    if kind == "open":
        h.stream_factory.side_effect = RuntimeError("open failed")
    elif kind == "load":
        h.factory.side_effect = RuntimeError("model missing")
    elif kind == "transcribe":
        h.model.transcribe.side_effect = RuntimeError("transcription failed")
    elif kind == "segments":
        def broken_segments():
            yield SimpleNamespace(text="partial")
            raise RuntimeError("decoding failed")
        h.model.transcribe.return_value = broken_segments(), None
    start(h)
    finish(h)
    assert h.results == []
    assert len(h.errors) == 1
    assert h.errors[0]
    if kind != "open":
        assert stream.closed
    h.stream_factory.side_effect = None
    h.factory.side_effect = None
    h.model.transcribe.side_effect = None
    h.model.transcribe.return_value = [SimpleNamespace(text="retry")], None
    stream.read = lambda size: (h.service.stop_recording() or block(), False)
    start(h)
    finish(h)
    assert h.results == ["retry"]
    assert len(h.errors) == 1


@pytest.mark.parametrize("volumes,times,settings,has_speech", [
    ([0, 0], [0, 1, 2], {"wait_for_speech_timeout": 2}, False),
    ([0.1, 0.1], [0, 1, 2], {"max_recording_duration": 2}, True),
    ([0.1, 0, 0.1, 0, 0], [0, 1, 2, 3, 4, 6], {"silence_duration": 2}, True),
])
def test_automatic_capture_limits(monkeypatch, volumes, times, settings, has_speech):
    chunks = iter(block(v) for v in volumes)
    stream = FakeStream(lambda size: (next(chunks), False))
    clock = iter(times)
    monkeypatch.setattr(speech.time, "monotonic", lambda: next(clock))
    service = speech.SpeechRecognitionService(stream_factory=lambda **kw: stream, **settings)
    audio = service._capture_audio()
    assert stream.closed
    if has_speech:
        np.testing.assert_array_equal(audio, np.concatenate([block(v) for v in volumes]).flatten())
    else:
        assert audio is None


def test_cancel_during_device_read_closes_stream_without_loading_model(harness):
    h = harness
    def read(size):
        h.service.cancel_recording()
        return block(), False
    stream = FakeStream(read)
    h.stream_factory.return_value = stream
    start(h)
    finish(h)
    assert stream.closed
    assert h.results == h.errors == []
    h.factory.assert_not_called()


def test_empty_capture_and_preexisting_stop_do_not_open_device(harness):
    h = harness
    h.service.stop_recording()
    assert h.service._capture_audio() is None
    h.stream_factory.assert_not_called()


def test_reuses_model_and_calls_back_on_worker(harness, monkeypatch):
    h = harness
    monkeypatch.setattr(h.service, "_capture_audio", lambda: block().flatten())
    callback_threads = []
    for _ in range(2):
        assert h.service.start_recording(lambda text: callback_threads.append(get_ident()))
        finish(h)
    assert len(callback_threads) == 2
    assert all(thread != get_ident() for thread in callback_threads)
    assert h.factory.call_count == 1


def test_thread_start_failure_restores_idle_state(harness, monkeypatch):
    h = harness
    with monkeypatch.context() as patch:
        patch.setattr(speech.threading.Thread, "start", Mock(side_effect=RuntimeError("start failed")))
        with pytest.raises(RuntimeError, match="start failed"):
            h.service.start_recording()
    assert not h.service.is_recording()
    monkeypatch.setattr(h.service, "_capture_audio", lambda: None)
    start(h)
    finish(h)
    assert h.results == [""]


def test_result_callback_error_still_restores_idle_state(harness, monkeypatch):
    h = harness
    monkeypatch.setattr(h.service, "_capture_audio", lambda: None)
    callback = Mock(side_effect=RuntimeError("callback failed"))
    assert h.service.start_recording(callback, h.errors.append)
    finish(h)
    assert h.errors == ["callback failed"]
