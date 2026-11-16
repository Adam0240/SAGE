
"""Unit tests for SAGE's text-to-speech service."""

import pytest

from PySide6.QtCore import QObject, Signal, QCoreApplication
from PySide6.QtTextToSpeech import QTextToSpeech

from services.text_to_speech_service import TextToSpeechService


class FakeVoice:
    """Represent an installed speech voice."""

    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class FakeSpeechEngine(QObject):
    """Simulate QTextToSpeech without playing audio."""

    stateChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self, voices=None):
        super().__init__()

        self.voices = voices or [
            FakeVoice("Microsoft Zira"),
            FakeVoice("Microsoft David"),
        ]

        self.selected_voice = None
        self.spoken_text = []
        self.stop_count = 0
        self.current_state = QTextToSpeech.State.Ready
        self.error_message = ""

    def availableVoices(self):
        return self.voices

    def setVoice(self, voice):
        self.selected_voice = voice

    def say(self, text):
        self.spoken_text.append(text)

    def stop(self):
        self.stop_count += 1

    def state(self):
        return self.current_state

    def errorString(self):
        return self.error_message


@pytest.fixture(scope="module")
def qt_app():
    """Provide a Qt application for signal testing."""
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def speech_service(qt_app):
    """Create the speech service with a fake engine."""
    engine = FakeSpeechEngine()

    service = TextToSpeechService(
        tts=engine,
        voice_name="Microsoft Zira",
    )

    return service, engine


def test_selects_zira_voice(speech_service):
    service, engine = speech_service

    assert engine.selected_voice is not None
    assert engine.selected_voice.name() == "Microsoft Zira"


def test_speak_valid_text(speech_service):
    service, engine = speech_service

    result = service.speak("Hello, I am SAGE.")

    assert result is True
    assert engine.spoken_text == ["Hello, I am SAGE."]


@pytest.mark.parametrize("text", ["", "   ", None, 123])
def test_speak_rejects_invalid_text(speech_service, text):
    service, engine = speech_service

    assert service.speak(text) is False
    assert engine.spoken_text == []


def test_stop_playback(speech_service):
    service, engine = speech_service

    service.speak("Testing speech.")
    service.stop()

    assert engine.stop_count == 1


def test_replay_previous_response(speech_service):
    service, engine = speech_service

    service.speak("Welcome to the STEAM Room.")

    assert service.replay() is True
    assert engine.spoken_text == [
        "Welcome to the STEAM Room.",
        "Welcome to the STEAM Room.",
    ]


def test_replay_without_previous_response(speech_service):
    service, engine = speech_service

    assert service.replay() is False
    assert engine.spoken_text == []


def test_speak_replaces_previous_response(speech_service):
    service, engine = speech_service

    service.speak("First response.")
    service.speak("Second response.")
    service.replay()

    assert engine.spoken_text == [
        "First response.",
        "Second response.",
        "Second response.",
    ]


def test_is_speaking(speech_service):
    service, engine = speech_service

    engine.current_state = QTextToSpeech.State.Speaking
    assert service.is_speaking() is True

    engine.current_state = QTextToSpeech.State.Ready
    assert service.is_speaking() is False


def test_state_changed_signal(speech_service):
    service, engine = speech_service

    states = []
    service.state_changed.connect(states.append)

    engine.stateChanged.emit(QTextToSpeech.State.Speaking)
    engine.stateChanged.emit(QTextToSpeech.State.Ready)

    assert states == ["speaking", "ready"]


def test_error_signal(speech_service):
    service, engine = speech_service

    errors = []
    service.error_occurred.connect(errors.append)

    engine.errorOccurred.emit(0, "Speech playback failed.")

    assert errors == ["Speech playback failed."]


def test_engine_error_prevents_speech(speech_service):
    service, engine = speech_service

    errors = []
    service.error_occurred.connect(errors.append)

    engine.current_state = QTextToSpeech.State.Error
    engine.error_message = "Speech engine unavailable."

    assert service.speak("Hello.") is False
    assert engine.spoken_text == []
    assert errors == ["Speech engine unavailable."]


def test_missing_voice_raises_error(qt_app):
    engine = FakeSpeechEngine(
        voices=[FakeVoice("Microsoft David")]
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        TextToSpeechService(
            tts=engine,
            voice_name="Microsoft Zira",
        )
