# SAGE Main UI

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from login_dialog import LoginDialog
from sage_apps.account_management_app import AccountManagementDialog
from sage_apps.gcode_display_print_app import GcodeDisplayPrintApp
from sage_apps.steamguide_app import SteamGuide_App
from services.session_service import SessionService
from services.speech_recognition_service import SpeechRecognitionService
from services.ai_response_worker import AIResponseLoader
from services.text_to_speech_service import TextToSpeechService


class SageWindow(QWidget):

    speech_recognized = Signal(int, str)
    speech_failed = Signal(int, str)
    speech_listening = Signal(int)

    def __init__(self, *, camera_controls=True):
        # Set up the QWidget before adding the SAGE window settings.
        super().__init__()

        # Initialize the application in Student Mode.
        self.session_service = SessionService()
        self.session_state = self.session_service.start()

        # Initialize voice recognition for the home screen.
        self.speech_service = SpeechRecognitionService(
            silence_duration=2.5,
            silence_threshold=0.005,
        )
        self._speech_request_id = 0
        self._speech_busy = False

        self.speech_recognized.connect(self.on_speech_recognized)
        self.speech_failed.connect(self.on_speech_failed)       

        self.gcode_window = None
        self.steamguide_window = None
        self.camera_controller = None
        self._camera_closing = False
        self._auto_camera = camera_controls
        self._camera_start_attempted = False
        self._camera_start_timer = QTimer(self)
        self._camera_start_timer.setSingleShot(True)
        self._camera_start_timer.timeout.connect(self.start_camera_controls)
        self.speech_listening.connect(self.on_speech_listening)

        # Process spoken questions using the existing STEAM Guide AI worker.
        self.tutorial_directory = (
            Path(__file__).resolve().parent / "STEAM_Tutorials"
        )

        self.ai_loader = AIResponseLoader(self)
        self.ai_loader.completed.connect(self.on_voice_ai_response)
        self._voice_ai_request = 0

        # Initialize spoken responses for the home screen.
        self.tts_service = None

        try:
            self.tts_service = TextToSpeechService(self)
            self.tts_service.error_occurred.connect(
                lambda error: print(f"Text-to-speech error: {error}")
            )
        except RuntimeError as error:
            print(f"Text-to-speech unavailable: {error}")

        self._tts_handoff_pending = False
        
        # Set the window title, starting size, and background color.
        self.setWindowTitle("SAGE")
        self.resize(1280, 720)
        self.setStyleSheet("background-color: black;")

        # Arrange the main parts of the screen from top to bottom.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 40)
        main_layout.setSpacing(0)

        # Arrange the title and mode button across the top.
        header_layout = QHBoxLayout()

        # Balance the button's width to keep the title centered.
        header_layout.addSpacing(180)

        title = QLabel("STEAM Artificial Guidance Expert")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: white; font-size: 36px; font-weight: bold;")
        header_layout.addWidget(title, stretch=1)

        # Display Student Mode by default.
        self.mode_button = QPushButton(self.session_state.button_label)
        self.mode_button.setFixedSize(180, 50)
        self.mode_button.clicked.connect(self.handle_mode_button)
        self.mode_button.setStyleSheet("""
            QPushButton {
                border: 4px solid black;
                border-radius: 0px;
                background-color: blue;
                color: white;
                font-size: 20px;
                font-weight: bold;
            }

            QPushButton:focus {
                border-color: red;
            }
        """)

        header_layout.addWidget(self.mode_button)
        main_layout.addLayout(header_layout)

        # Leave flexible space between the title and the avatar.
        main_layout.addStretch(2)

        # Use three dots as a placeholder for the AI avatar.
        self.avatar = QLabel("●   ●   ●")
        self.avatar.setFixedSize(200, 200)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setStyleSheet("""
            border: 4px solid white;
            border-radius: 100px;
            font-size: 24px;
        """)

        main_layout.addWidget(
            self.avatar,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        # Leave a gap between the avatar and the application buttons.
        # Add voice interaction controls below the AI avatar.
        main_layout.addSpacing(20)

        self.talk_button = QPushButton("Talk to SAGE")
        self.talk_button.setObjectName("talkToSageButton")
        self.talk_button.setAccessibleName("Talk to SAGE")
        self.talk_button.setFixedSize(250, 60)
        self.talk_button.setStyleSheet("""
            QPushButton {
                background-color: blue;
                color: white;
                border: 2px solid white;
                border-radius: 15px;
                font-size: 22px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #3366cc;
            }

            QPushButton:focus {
                border-color: red;
            }
        """)

        self.talk_button.clicked.connect(self.toggle_speech)

        main_layout.addWidget(
            self.talk_button,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        # Display microphone status and recognized questions.
        self.voice_status_label = QLabel("Voice assistant ready")
        self.voice_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_status_label.setWordWrap(True)
        self.voice_status_label.setFixedWidth(750)
        self.voice_status_label.setMinimumHeight(60)
        self.voice_status_label.setStyleSheet(
            "color: white; font-size: 18px;"
        )

        main_layout.addWidget(
            self.voice_status_label,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        main_layout.addSpacing(20)

        # Arrange the three application buttons in a centered row.
        app_layout = QHBoxLayout()
        app_layout.setSpacing(40)
        app_layout.addStretch()

        # Keep the buttons in a list so we can use them later.
        self.app_buttons = []

        for index in range(3):
            button = QPushButton()
            button.setFixedSize(130, 130)
            button.setAccessibleName(f"Application {index + 1}")

            # Half of the button's width is used as the border radius
            # to give the square button a circular appearance.
            button.setStyleSheet("""
                QPushButton {
                    border: 4px solid black;
                    border-radius: 65px;
                    background-color: blue;
                }

                QPushButton:hover {
                    border-color: #336699;
                }

                QPushButton:focus {
                    border-color: red;
                }
            """)

            self.app_buttons.append(button)
            app_layout.addWidget(button)

        # Replace the first two blue circles with the application images.
        icon_dir = Path(__file__).resolve().parent / "resources" / "app_icons"
        for button, filename in zip(
            self.app_buttons, ("useradmin_appicon.png", "gcode_appicon.png")
        ):
            button.setIcon(QIcon(str(icon_dir / filename)))
            button.setIconSize(QSize(110, 110))
            button.setStyleSheet(
                button.styleSheet().replace(
                    "background-color: blue;", "background-color: transparent;"
                )
            )

        # The first button opens account management after staff login.
        self.app_buttons[0].setAccessibleName("Account Management")
        self.app_buttons[0].setToolTip("Account Management")
        self.app_buttons[0].clicked.connect(self.open_account_management)
        self.app_buttons[0].setEnabled(False)

        # The second button opens the G-code viewer in Student Mode or a staff session.
        self.app_buttons[1].setAccessibleName("3D Printing")
        self.app_buttons[1].setToolTip("3D Printing")
        self.app_buttons[1].clicked.connect(self.open_gcode_app)

        # The third button opens the STEAM Guide for students and staff.
        self.app_buttons[2].setText("STEAM\nGuide")
        self.app_buttons[2].setAccessibleName("STEAM Guide")
        self.app_buttons[2].setToolTip("STEAM Guide")
        self.app_buttons[2].setStyleSheet(
            self.app_buttons[2].styleSheet()
            + "QPushButton { color: white; font-size: 20px; font-weight: bold; }"
        )
        self.app_buttons[2].clicked.connect(self.open_steamguide_app)

        app_layout.addStretch()
        main_layout.addLayout(app_layout)

        # Leave flexible space below the application buttons.
        main_layout.addStretch(1)

    
    def toggle_speech(self):
        """Start recording or stop the current recording."""
        if self._speech_busy:
            self.speech_service.stop_recording()
            self.talk_button.setEnabled(False)
            self.voice_status_label.setText("Transcribing...")
            return

        if self.tts_service is not None:
            if self.tts_service.is_speaking():
                self.tts_service.stop()
                self._tts_handoff_pending = True
                self.talk_button.setEnabled(False)
                self.voice_status_label.setText("Preparing microphone...")

                QTimer.singleShot(350, self.start_speech_after_tts)
                return

        self._speech_request_id += 1
        request_id = self._speech_request_id

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
            self.voice_status_label.setText(f"Microphone error: {error}")
            return

        if not started:
            self.voice_status_label.setText(
                "Previous recording is still finishing. Try again."
            )
            return

        self._speech_busy = True
        self.talk_button.setText("Stop Recording")
        self.voice_status_label.setText("Starting microphone...")

    def start_speech_after_tts(self):
        """Start recording after the previous audio playback has stopped."""
        if not self._tts_handoff_pending:
            return

        self._tts_handoff_pending = False
        self.talk_button.setEnabled(True)
        self.toggle_speech()
    
    @Slot(int)
    def on_speech_listening(self, request_id):
        """Update the interface when the microphone is ready."""
        if request_id != self._speech_request_id:
            return

        if not self._speech_busy:
            return

        self.voice_status_label.setText("Listening...")
    
    @Slot(int, str)
    def on_speech_recognized(self, request_id, transcript):
        """Send recognized speech to SAGE's existing AI assistant."""
        if request_id != self._speech_request_id:
            return

        self._speech_busy = False
        self.talk_button.setText("Talk to SAGE")

        question = transcript.strip()

        if not question:
            self.talk_button.setEnabled(True)
            self.voice_status_label.setText(
                "No speech detected. Please try again."
            )
            return

        self.talk_button.setEnabled(False)
        self.voice_status_label.setText(
            f"You said: {question}\nSAGE is thinking..."
        )

        self._voice_ai_request = self.ai_loader.submit(
            question,
            self.tutorial_directory,
        )

    @Slot(int, object)
    def on_voice_ai_response(self, request_id, response):
        """Display and speak the answer returned by the AI worker."""
        if request_id != self._voice_ai_request:
            return

        answer = response.spoken_text or response.markdown

        print(f"SAGE answer: {answer}")

        # Display a short preview on the home screen.
        preview = answer[:160]
        if len(answer) > 160:
            preview += "..."

        self.voice_status_label.setText(f"SAGE: {preview}")
        self.talk_button.setEnabled(True)

        # Speak the answer using Microsoft Zira.
        if self.tts_service is not None:
            self.tts_service.speak(answer)

    @Slot(int, str)
    def on_speech_failed(self, request_id, error):
        """Display microphone or recognition errors."""
        if request_id != self._speech_request_id:
            return

        self._speech_busy = False
        self.talk_button.setEnabled(True)
        self.talk_button.setText("Talk to SAGE")
        self.voice_status_label.setText(
            f"Speech recognition error: {error}"
        )

    def cancel_speech(self):
        """Cancel voice input when leaving the home screen."""
        self._tts_handoff_pending = False
        self._speech_request_id += 1
        self.speech_service.cancel_recording()
        self._speech_busy = False

        self.talk_button.setEnabled(True)
        self.talk_button.setText("Talk to SAGE")
        self.voice_status_label.setText("Voice assistant ready")
        self.ai_loader.cancel()
        self._voice_ai_request = 0

        if self.tts_service is not None:
            self.tts_service.stop()


    def showEvent(self, event):
        super().showEvent(event)
        if self._auto_camera and not self._camera_start_attempted:
            self._camera_start_timer.start(0)

    def start_camera_controls(self):
        if self._camera_start_attempted or self._camera_closing or not self.isVisible():
            return
        self._camera_start_attempted = True
        if self.camera_controller is None:
            # Start after Home has a screen, so calibration uses its actual display.
            try:
                from TouchControls.home_input import HomeInputController
            except (ImportError, OSError) as error:
                self.show_camera_error(
                    f"Camera dependencies unavailable. Install requirements.txt. ({error})"
                )
                return
            self.camera_controller = HomeInputController(self)
            self.camera_controller.error_occurred.connect(self.show_camera_error)
            self.camera_controller.stopped.connect(self.camera_stopped)
        self.camera_controller.start()

    def show_camera_error(self, message):
        if self._camera_closing:
            return
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Camera controls unavailable",
                             message + "\n\nMouse and keyboard controls remain available.",
                             QMessageBox.StandardButton.Ok, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()

    def camera_stopped(self):
        if self._camera_closing:
            self.close()

    def handle_mode_button(self):
        # Clicking the mode button while logged in returns to Student Mode.
        if self.session_state.user_id is not None:
            self.session_state = self.session_service.log_out()
            self.mode_button.setText(self.session_state.button_label)
            self.app_buttons[0].setEnabled(False)
            return

        # Student Mode opens the administrator login dialog.
        dialog = LoginDialog(self)

        try:
            result = dialog.exec()
            if result == LoginDialog.DialogCode.Accepted:
                self.session_state = self.session_service.log_in(
                    user_id=dialog.user_id,
                    user_name=dialog.user_name,
                    role=dialog.user_role,
                )
                self.mode_button.setText(self.session_state.button_label)
                self.app_buttons[0].setEnabled(True)
        finally:
            # Copy accepted identity before releasing the modal dialog.
            dialog.deleteLater()

    def open_account_management(self):
        # Account management is available only during a staff session.
        if self.session_state.user_id is None:
            return

        dialog = AccountManagementDialog(
            actor_id=self.session_state.user_id,
            actor_role=self.session_state.mode,
            parent=self,
        )
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    # Reuse the viewer so returning home does not discard the selected file.
    def open_gcode_app(self):
        self.cancel_speech()
        if self.gcode_window is None:
            self.gcode_window = GcodeDisplayPrintApp(parent=self)
            self.gcode_window.setWindowFlag(Qt.WindowType.Window, True)
            self.gcode_window.home_requested.connect(self.show_home)
        self.gcode_window.show()
        self.gcode_window.raise_()
        self.gcode_window.activateWindow()
        self.hide()

    # Reuse the guide so returning home preserves the question and response.
    def open_steamguide_app(self):
        self.cancel_speech()
        if self.steamguide_window is None:
            self.steamguide_window = SteamGuide_App(parent=self)
            self.steamguide_window.setWindowFlag(Qt.WindowType.Window, True)
            self.steamguide_window.home_requested.connect(self.show_home)
        self.steamguide_window.show()
        self.steamguide_window.raise_()
        self.steamguide_window.activateWindow()
        self.hide()

    # Restore the existing home window and its current login session.
    def show_home(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # Closing SAGE also hides its apps without requesting another return home.
    def closeEvent(self, event):
        self.cancel_speech()
        self._camera_start_timer.stop()
        if self.camera_controller is not None and self.camera_controller.worker is not None:
            self._camera_closing = True
            self.camera_controller.stop()
            event.ignore()
            return
        if self.gcode_window is not None:
            self.gcode_window.hide()
        if self.steamguide_window is not None:
            self.steamguide_window.hide()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        # End the application when the Escape key is pressed.
        if event.key() == Qt.Key.Key_Escape:
            if self.camera_controller is not None and self.camera_controller.worker is not None:
                self.close()
            else:
                QApplication.quit()
        else:
            # Keep the default behavior for other keys.
            super().keyPressEvent(event)


if __name__ == "__main__":
    # Start the Qt application.
    app = QApplication(sys.argv)

    # Create the SAGE window and display it.
    window = SageWindow()
    window.show()

    # Keep the application running so it can respond to user input.
    sys.exit(app.exec())
