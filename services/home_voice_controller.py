"""Home voice lifecycle, independent of the window's widgets and navigation."""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from services.ai_response_worker import AIResponseLoader
from services.speech_recognition_service import SpeechRecognitionService
from services.text_to_speech_service import TextToSpeechService
from services.octoprint_file_service import OctoPrintFileService
from services.project_search_service import ProjectSearchService
from services.voice_command_service import VoiceCommandService


class HomeSpeechRecognitionService(SpeechRecognitionService):
    """Notify the home screen when automatic capture ends, before Whisper runs."""

    def _capture_audio(self):
        on_captured = self.on_captured
        audio = super()._capture_audio()
        on_captured()
        return audio


class HomeVoiceController(QObject):
    button_changed = Signal(str, bool)
    avatar_changed = Signal(str)
    error_occurred = Signal(str)

    speech_recognized = Signal(int, str)
    speech_failed = Signal(int, str)
    speech_listening = Signal(int)
    speech_transcribing = Signal(int)

    project_open_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closing = False
        self._button_text = "Talk to SAGE"
        self._button_enabled = True

        # Initialize voice recognition for the home screen.
        self.speech_service = HomeSpeechRecognitionService(
            silence_duration=2.5,
            silence_threshold=0.005,
        )
        self._speech_request_id = 0
        self._speech_busy = False

        self.speech_recognized.connect(self.on_speech_recognized)
        self.speech_listening.connect(self.on_speech_listening)
        self.speech_transcribing.connect(self.on_speech_transcribing)
        self.speech_failed.connect(self.on_speech_failed)

        # Process spoken questions using the existing STEAM Guide AI worker.
        self.tutorial_directory = (
            Path(__file__).resolve().parent.parent / "STEAM_Tutorials"
        )

        self.ai_loader = AIResponseLoader(self)
        self.ai_loader.completed.connect(self.on_voice_ai_response)
        self._voice_ai_request = 0

        # Initialize voice command processing.
        self.voice_command_service = VoiceCommandService()
        self.project_search_service = ProjectSearchService()

        # Initialize read-only access to the OctoPrint file library.
        self.project_file_service = OctoPrintFileService(
            Path(__file__).resolve().parent.parent
            / "sage_apps" / "thumbnails" / "gcodes",
            self,
        )

        self.project_file_service.library_loaded.connect(
            self.on_project_library_loaded
        )

        self.project_file_service.failed.connect(
            self.on_project_library_failed
        )

        # Track the current project search request.
        self._project_search_query = None
        self._project_open_on_match = False

        # Retain search results for follow-up voice commands.
        self._project_matches = []
        self._project_search_source = ""

        # Initialize spoken responses for the home screen.
        self.tts_service = None
        self._tts_error = None

        try:
            self.tts_service = TextToSpeechService(self)
            self.tts_service.state_changed.connect(self.on_tts_state_changed)
            self.tts_service.error_occurred.connect(
                self.on_tts_error
            )
        except RuntimeError as error:
            self._tts_error = str(error)
            print(f"Text-to-speech unavailable: {error}")

        self._tts_handoff_pending = False
        self._awaiting_tts_completion = False
        self._tts_handoff_timer = QTimer(self)
        self._tts_handoff_timer.setSingleShot(True)
        self._tts_handoff_timer.setInterval(350)
        self._tts_handoff_timer.timeout.connect(self.start_speech_after_tts)

        # Animate the avatar while SAGE generates an AI response.
        self._thinking_frames = (
            "●",
            "●   ●",
            "●   ●   ●",
        )
        self._thinking_frame_index = 0

        self.thinking_timer = QTimer(self)
        self.thinking_timer.setInterval(350)
        self.thinking_timer.timeout.connect(self.advance_thinking_animation)


    def start_thinking_animation(self):
        """Start animating the avatar while SAGE processes a question."""
        self._thinking_frame_index = 0
        self.avatar_changed.emit(self._thinking_frames[0])
        self.thinking_timer.start()


    def advance_thinking_animation(self):
        """Cycle through one, two, and three dots."""
        self._thinking_frame_index = (
            self._thinking_frame_index + 1
        ) % len(self._thinking_frames)

        self.avatar_changed.emit(
            self._thinking_frames[self._thinking_frame_index]
        )


    def stop_thinking_animation(self):
        """Stop the animation and restore the original avatar."""
        self.thinking_timer.stop()
        self._thinking_frame_index = 0
        self.avatar_changed.emit("●   ●   ●")


    def _set_button(self, text, enabled):
        self._button_text = text
        self._button_enabled = enabled
        self.button_changed.emit(text, enabled)

    def toggle_speech(self):
        """Start recording or stop the current recording."""
        if self._closing or not self._button_enabled:
            return
        if self._speech_busy:
            self.on_speech_transcribing(self._speech_request_id)
            self.speech_service.stop_recording()
            return

        if self.tts_service is not None:
            if self._awaiting_tts_completion or self.tts_service.is_speaking():
                self._awaiting_tts_completion = False
                self.tts_service.stop()
                self.stop_thinking_animation()
                self._tts_handoff_pending = True
                self._set_button("Starting microphone...", False)

                self._tts_handoff_timer.start()
                return

        self._speech_request_id += 1
        request_id = self._speech_request_id
        self._speech_busy = True
        self._set_button("Starting microphone...", False)
        self.speech_service.on_captured = lambda: self.speech_transcribing.emit(request_id)

        try:
            started = self.speech_service.start_recording(
                on_result=lambda text: self.speech_recognized.emit(
                    request_id, text
                ),
                on_error=lambda error: self.speech_failed.emit(
                    request_id, error
                ),
                on_ready=lambda: self.speech_listening.emit(request_id),
            )
        except Exception as error:
            self.on_speech_failed(request_id, f"Microphone error: {error}")
            return

        if not started:
            self.on_speech_failed(request_id, "Previous recording is still finishing. Try again.")
            return

    @Slot(int)
    def on_speech_listening(self, request_id):
        """Enable recording controls only once the microphone delivers audio."""
        if (request_id == self._speech_request_id and self._speech_busy
                and self._button_text == "Starting microphone..."):
            self._set_button("Listening...", True)

    @Slot(int)
    def on_speech_transcribing(self, request_id):
        if request_id == self._speech_request_id and self._speech_busy:
            self._set_button("Transcribing...", False)

    def start_speech_after_tts(self):
        """Start recording after the previous audio playback has stopped."""
        if self._closing or not self._tts_handoff_pending:
            return

        self._tts_handoff_pending = False
        self._set_button(self._button_text, True)
        self.toggle_speech()

    @Slot(int, str)
    def on_speech_recognized(self, request_id, transcript):
        """Process recognized speech and route supported voice commands."""
        if request_id != self._speech_request_id:
            return

        self._speech_busy = False
        self._set_button("Talk to SAGE", self._button_enabled)

        question = transcript.strip()

        if not question:
            self._set_button(self._button_text, True)
            return

        print(f"User: {question}")
        self._set_button("SAGE is thinking...", False)

        self.start_thinking_animation()

        # Check whether the user is selecting a previous search result.
        selection = self.voice_command_service.get_project_selection(
            question
        )

        if selection is not None:
            if self.handle_project_selection(selection):
                return

        # Determine whether the user is searching for a saved project.
        project_query = (
            self.voice_command_service.get_project_search_query(
                question
            )
        )

        if project_query is not None:
            self.search_saved_projects(
                project_query,
                open_on_match=selection is not None,
            )
            return

        # Clear previous project results when changing topics.
        self._project_matches = []
        self._project_search_source = ""

        # Send general questions to the existing AI assistant.
        try:
            self._voice_ai_request = self.ai_loader.submit(
                question,
                self.tutorial_directory,
            )
        except Exception as error:
            self.on_speech_failed(request_id, str(error))

    def handle_project_selection(self, selection):
        """Handle a request to display a previous search result."""

        if not self._project_matches:
            return False

        # Check whether the user selected a numbered result.
        index = self.voice_command_service.get_selection_index(
            selection
        )

        if index is not None:
            if index >= len(self._project_matches):
                self.speak_response(
                    "That project number is not available."
                )
                return True

            self.open_selected_project(
                self._project_matches[index]
            )
            return True

        # Otherwise, attempt to locate the project by name.
        matches = self.project_search_service.find_selection(
            selection,
            self._project_matches,
        )

        if len(matches) == 1:
            self.open_selected_project(matches[0])
            return True

        if len(matches) > 1:
            self.speak_response(
                "Several projects match that name. "
                "Please provide a more specific project name "
                "or select a numbered option."
            )
            return True

        return False


    def open_selected_project(self, entry):
        """Request that SAGE display the selected OctoPrint project."""

        print(f"Opening saved project: {entry.path}")

        self.project_open_requested.emit(
            entry.path,
            self._project_search_source,
        )
    
    def search_saved_projects(self, query, *, open_on_match=False):
        """Retrieve the current OctoPrint project library."""

        self._project_search_query = query
        self._project_open_on_match = open_on_match

        # Clear results from the previous search.
        self._project_matches = []
        self._project_search_source = ""

        self._set_button("Searching projects...", False)

        print(f"Searching saved projects for: {query}")

        self.project_file_service.load_library()


    @Slot(object)
    def on_project_library_loaded(self, folders):
        """Search the retrieved OctoPrint project library."""

        if self._closing or self._project_search_query is None:
            return

        query = self._project_search_query
        open_on_match = self._project_open_on_match

        self._project_search_query = None
        self._project_open_on_match = False

        # Search the retrieved filenames.
        matches = self.project_search_service.search(
            query,
            folders,
        )

        # Retain results for subsequent voice commands.
        self._project_matches = matches
        self._project_search_source = (
            self.project_file_service.library_source
        )

        # Open a unique project when explicitly requested.
        if open_on_match and len(matches) == 1:
            self.open_selected_project(matches[0])
            return

        # Generate a response using the actual search results.
        response = self.project_search_service.create_response(
            query,
            matches,
        )

        print(f"SAGE answer: {response}")

        self.speak_response(response)


    @Slot(str, str)
    def on_project_library_failed(self, kind, message):
        """Handle unavailable OctoPrint project information."""

        if (
            self._closing
            or kind != "library"
            or self._project_search_query is None
        ):
            return

        self._project_search_query = None
        self._project_open_on_match = False

        print(f"OctoPrint project search error: {message}")

        self.speak_response(
            "I am currently unable to access the saved "
            "3D printing projects in OctoPrint. "
            "Please check the OctoPrint connection."
        )

    @Slot(int, object)
    def on_voice_ai_response(self, request_id, response):
        """Speak the answer returned by the AI worker."""
        if not self._voice_ai_request or request_id != self._voice_ai_request:
            return
        self._voice_ai_request = 0

        answer = response.spoken_text or response.markdown

        print(f"SAGE answer: {answer}")

        self.speak_response(answer)


    def speak_response(self, answer):
        """Speak a response using the text-to-speech service."""
        self._set_button("Talk to SAGE", True)

        # Speak the answer using Microsoft Zira.
        # Keep the animation running while Zira speaks.
        if self.tts_service is not None:
            self._awaiting_tts_completion = True

            self._tts_error = None
            try:
                if self.tts_service.speak(answer):
                    return
            except Exception as error:
                self.on_tts_error(str(error))

            if self._tts_error is None:
                self.on_tts_error("Speech playback could not start.")

            self._awaiting_tts_completion = False
        else:
            self.report_error(
                self._tts_error or "Text-to-speech is unavailable."
            )

        # Stop if text-to-speech is unavailable or fails to start.
        self.stop_thinking_animation()

    def speak_startup_greeting(self):
        """Greet the user when SAGE is initially started."""
        if self._closing or self.tts_service is None:
            return

        self.start_thinking_animation()

        self.speak_response(
            "Hello, and welcome to the STEAM Room. "
            "I am SAGE, your STEAM Artificial Guidance Expert. "
            "How can I assist you today?"
        )
    
    @Slot(int, str)
    def on_speech_failed(self, request_id, error):
        """Report microphone or recognition errors and restore the button."""
        if request_id != self._speech_request_id:
            return

        self._speech_busy = False
        self.stop_thinking_animation()
        self._set_button("Talk to SAGE", True)

        # Preserve the original error for troubleshooting.
        print(f"Speech recognition error: {error}")

        # Provide a user-friendly message for missing microphone devices.
        if "error querying device" in error.lower():
            message = (
                "Unable to access the microphone. "
                "Please check that it is connected and selected "
                "as the Windows input device, then try again."
            )
        else:
            message = error

        self.report_error(message)


    def report_error(self, message):
        """Send errors to the home screen unless SAGE is closing."""
        if not self._closing:
            self.error_occurred.emit(message)
    
    @Slot(str)
    def on_tts_error(self, error):
        if self._closing or not self._awaiting_tts_completion:
            return
        self._tts_error = error
        if self._awaiting_tts_completion:
            self._awaiting_tts_completion = False
            self.stop_thinking_animation()
            self._set_button("Talk to SAGE", True)
        self.report_error(error)

    def cancel(self):
        """Cancel voice input when leaving the home screen."""
        self._tts_handoff_timer.stop()
        self._tts_handoff_pending = False
        self._speech_request_id += 1
        self.speech_service.cancel_recording()
        self._speech_busy = False

        self._set_button("Talk to SAGE", not self._closing)
        self.ai_loader.cancel()
        self._voice_ai_request = 0

        # Cancel any active OctoPrint project search.
        self._project_search_query = None
        self._project_open_on_match = False
        self._project_matches = []
        self._project_search_source = ""

        self.project_file_service.cancel()

        self._awaiting_tts_completion = False
        self.stop_thinking_animation()

        if self.tts_service is not None:
            self.tts_service.stop()


    @Slot(str)
    def on_tts_state_changed(self, state):
        """Stop the avatar animation when spoken playback finishes."""
        if self._closing or not self._awaiting_tts_completion:
            return

        if state in ("ready", "error"):
            # Keep error reporting active until the engine supplies its error message.
            if state == "ready":
                self._awaiting_tts_completion = False
            self.stop_thinking_animation()
            self._set_button("Talk to SAGE", True)

    def shutdown(self):
        """Prevent new work and cancel the active voice interaction."""
        self._closing = True
        self.cancel()
