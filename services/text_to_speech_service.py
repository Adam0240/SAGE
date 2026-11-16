
"""Text-to-speech service for SAGE using PySide6."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtTextToSpeech import QTextToSpeech


class TextToSpeechService(QObject):
    state_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        parent=None,
        engine="winrt",
        voice_name="Microsoft Zira",
        tts=None,
    ):
        super().__init__(parent)

        self._last_text = ""

        # Create the speech engine or use an injected test engine.
        if tts is None:
            if engine not in QTextToSpeech.availableEngines():
                raise RuntimeError(
                    f"Speech engine '{engine}' is unavailable."
                )

            tts = QTextToSpeech(engine, self)

        self._tts = tts

        # Connect Qt speech events.
        self._tts.stateChanged.connect(self._handle_state)
        self._tts.errorOccurred.connect(self._handle_error)

        # Select the requested voice.
        voices = self._tts.availableVoices()

        selected_voice = next(
            (voice for voice in voices
             if voice.name() == voice_name),
            None,
        )

        if selected_voice is None:
            raise RuntimeError(
                f"Speech voice '{voice_name}' is unavailable."
            )

        self._tts.setVoice(selected_voice)

    def speak(self, text):
        """Speak a new response."""
        if not isinstance(text, str) or not text.strip():
            return False

        if self._tts.state() == QTextToSpeech.State.Error:
            self.error_occurred.emit(
                self._tts.errorString() or "Speech engine unavailable."
            )
            return False

        self._last_text = text.strip()
        self._tts.say(self._last_text)

        return True

    def stop(self):
        """Stop the current spoken response."""
        self._tts.stop()

    def replay(self):
        """Repeat the most recent response."""
        if not self._last_text:
            return False

        return self.speak(self._last_text)

    def is_speaking(self):
        """Check whether SAGE is currently speaking."""
        return self._tts.state() == QTextToSpeech.State.Speaking

    def _handle_state(self, state):
        """Notify listeners when playback state changes."""
        self.state_changed.emit(state.name.lower())

    def _handle_error(self, reason, message):
        """Report speech engine and playback errors."""
        self.error_occurred.emit(
            message or "An error occurred during speech playback."
        )
