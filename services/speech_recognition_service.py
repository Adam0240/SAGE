
import threading
import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


class SpeechRecognitionService:
    def __init__(
        self,
        model_size="base.en",
        sample_rate=16000,
        silence_duration=1.5,
        silence_threshold=0.015,
        max_recording_duration=20,
        wait_for_speech_timeout=10,
    ):
        self.sample_rate = sample_rate
        self.silence_duration = silence_duration
        self.silence_threshold = silence_threshold
        self.max_recording_duration = max_recording_duration
        self.wait_for_speech_timeout = wait_for_speech_timeout

        self.model_size = model_size
        self.model = None

        self._recording_thread = None
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._is_recording = False

    def _load_model(self):
        """Load the local speech recognition model when needed."""
        if self.model is None:
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                local_files_only=True,
            )

    def start_recording(self, on_result=None, on_error=None):
        """Start recording in a background thread."""
        with self._lock:
            if self._is_recording:
                return False

            self._is_recording = True
            self._stop_event.clear()
            self._cancel_event.clear()

            self._recording_thread = threading.Thread(
                target=self._record_and_transcribe,
                args=(on_result, on_error),
                daemon=True,
            )
            self._recording_thread.start()

        return True

    def stop_recording(self):
        """Stop recording and transcribe the captured audio."""
        self._stop_event.set()

    def cancel_recording(self):
        """Cancel recording without returning a transcript."""
        self._cancel_event.set()
        self._stop_event.set()

    def is_recording(self):
        """Return whether the service is currently busy."""
        with self._lock:
            return self._is_recording

    def _record_and_transcribe(self, on_result, on_error):
        """Capture microphone audio and transcribe it."""
        try:
            audio = self._capture_audio()

            if self._cancel_event.is_set():
                return

            if audio is None:
                if on_result:
                    on_result("")
                return

            self._load_model()

            if self._cancel_event.is_set():
                return

            segments, _ = self.model.transcribe(
                audio,
                language="en",
                beam_size=5,
            )

            transcript = " ".join(
                segment.text.strip()
                for segment in segments
            )

            if not self._cancel_event.is_set() and on_result:
                on_result(transcript)

        except Exception as error:
            if not self._cancel_event.is_set() and on_error:
                on_error(str(error))

        finally:
            with self._lock:
                self._is_recording = False

    def _capture_audio(self):
        """Record until silence, timeout, or manual stop."""
        audio_chunks = []
        speech_detected = False
        silence_start = None
        start_time = time.monotonic()

        block_duration = 0.1
        block_size = int(self.sample_rate * block_duration)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        ) as stream:

            while not self._stop_event.is_set():
                audio, overflowed = stream.read(block_size)

                if overflowed:
                    raise RuntimeError(
                        "Microphone audio overflow detected."
                    )

                audio_chunks.append(audio.copy())

                volume = np.sqrt(np.mean(audio ** 2))
                current_time = time.monotonic()

                if volume > self.silence_threshold:
                    speech_detected = True
                    silence_start = None

                elif speech_detected:
                    if silence_start is None:
                        silence_start = current_time

                    if (
                        current_time - silence_start
                        >= self.silence_duration
                    ):
                        break

                if (
                    current_time - start_time
                    >= self.max_recording_duration
                ):
                    break

                if (
                    not speech_detected
                    and current_time - start_time
                    >= self.wait_for_speech_timeout
                ):
                    break

        if self._cancel_event.is_set() or not audio_chunks:
            return None

        if not speech_detected and not self._stop_event.is_set():
            return None

        return np.concatenate(audio_chunks).flatten()
