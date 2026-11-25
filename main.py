# SAGE Main UI

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Slot
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
from services.home_voice_controller import HomeVoiceController
from services.session_service import SessionService


class SageWindow(QWidget):

    def __init__(self, *, camera_controls=True):
        # Set up the QWidget before adding the SAGE window settings.
        super().__init__()

        # Initialize the application in Student Mode.
        self.session_service = SessionService()
        self.session_state = self.session_service.start()

        self.gcode_window = None
        self.steamguide_window = None
        self.camera_controller = None
        self._camera_closing = False
        self._closing = False
        self._auto_camera = camera_controls
        self._camera_start_attempted = False
        self._camera_start_timer = QTimer(self)
        self._camera_start_timer.setSingleShot(True)
        self._camera_start_timer.timeout.connect(self.start_camera_controls)

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

        main_layout.addWidget(
            self.talk_button,
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

        self.voice_controller = HomeVoiceController(self)
        self.voice_controller.button_changed.connect(self.update_voice_button)
        self.voice_controller.avatar_changed.connect(self.avatar.setText)
        self.voice_controller.error_occurred.connect(self.show_voice_error)
        self.voice_controller.project_open_requested.connect(
            self.open_voice_project
        )
        self.talk_button.clicked.connect(self.voice_controller.toggle_speech)


    @Slot(str, bool)
    def update_voice_button(self, text, enabled):
        """Keep the visible and accessible voice states synchronized."""
        self.talk_button.setText(text)
        self.talk_button.setAccessibleName(text)
        self.talk_button.setEnabled(enabled and not self._closing)

    @Slot(str)
    def show_voice_error(self, message):
        if self._closing or not self.isVisible():
            return
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Voice assistant unavailable",
                             message, QMessageBox.StandardButton.Ok, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()

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
        if self._closing:
            return
        self.voice_controller.cancel()
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
        if self._closing or self.session_state.user_id is None:
            return

        self.voice_controller.cancel()

        dialog = AccountManagementDialog(
            actor_id=self.session_state.user_id,
            actor_role=self.session_state.mode,
            parent=self,
        )
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def open_gcode_app(self):
        """Open the 3D printing application normally."""
        self._open_gcode_app()


    @Slot(str, str)
    def open_voice_project(self, path, source):
        """Open a project selected through a voice command."""
        self._open_gcode_app(project=(path, source))


    # Reuse the viewer so returning home does not discard the selected file.
    def _open_gcode_app(self, project=None):
        if self._closing:
            return

        # Prevent changing projects while submitting a print.
        if (
            project is not None
            and self.gcode_window is not None
            and self.gcode_window.print_service.busy
        ):
            self.voice_controller.speak_response(
                "A print request is currently being processed."
            )
            return

        self.voice_controller.cancel()

        if self.gcode_window is None:
            self.gcode_window = GcodeDisplayPrintApp(
                parent=self,
                can_start_print=lambda: (
                    not self._closing
                    and self.session_state.can_start_print
                ),
                get_session=lambda: self.session_state,
            )
            self.gcode_window.print_service.authorization_revoked.connect(
                self.invalidate_print_session)

            self.gcode_window.setWindowFlag(
                Qt.WindowType.Window, True
            )

            self.gcode_window.home_requested.connect(
                self.show_home
            )

        self.gcode_window.show()
        self.gcode_window.raise_()
        self.gcode_window.activateWindow()

        # Open the project requested through voice interaction.
        if project is not None:
            self.gcode_window.open_voice_project(*project)

        self.hide()

    @Slot(object)
    def invalidate_print_session(self, session):
        # A late result must never log out a replacement staff session.
        if self.session_state is session:
            self.session_state = self.session_service.log_out()
            self.mode_button.setText(self.session_state.button_label)
            self.app_buttons[0].setEnabled(False)

    # Reuse the guide so returning home preserves the question and response.
    def open_steamguide_app(self):
        if self._closing:
            return
        self.voice_controller.cancel()
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
        if self._closing:
            return
        self.show()
        self.raise_()
        self.activateWindow()

    # Closing SAGE also hides its apps without requesting another return home.
    def closeEvent(self, event):
        self._closing = True
        self.setEnabled(False)
        self.voice_controller.shutdown()
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
                self._closing = True
                self.setEnabled(False)
                self.voice_controller.shutdown()
                QApplication.quit()
        else:
            # Keep the default behavior for other keys.
            super().keyPressEvent(event)



if __name__ == "__main__":
    # Support the speech subprocess in Windows packaged builds.
    from multiprocessing import freeze_support
    freeze_support()
    # Start the Qt application.
    app = QApplication(sys.argv)

    # Create the SAGE window and display it.
    window = SageWindow()
    window.show()

    # Provide a voice greeting when SAGE starts.
    QTimer.singleShot(
        0, window.voice_controller.speak_startup_greeting
    )

    # Keep the application running so it can respond to user input.
    sys.exit(app.exec())
