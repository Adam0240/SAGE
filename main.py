# SAGE Main UI

import sys
from PySide6.QtCore import Qt
from login_dialog import LoginDialog
from services.session_service import SessionService
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SageWindow(QWidget):
    def __init__(self):
        # Set up the QWidget before adding the SAGE window settings.
        super().__init__()

        # Initialize the application in Student Mode.
        self.session_service = SessionService()
        self.session_state = self.session_service.start()

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
        title.setStyleSheet("font-size: 36px; font-weight: bold;")
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
        main_layout.addSpacing(40)

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

        app_layout.addStretch()
        main_layout.addLayout(app_layout)

        # Leave flexible space below the application buttons.
        main_layout.addStretch(1)

    def handle_mode_button(self):
        # Clicking the mode button while logged in returns to Student Mode.
        if self.session_state.user_id is not None:
            self.session_state = self.session_service.log_out()
            self.mode_button.setText(self.session_state.button_label)
            return

        # Student Mode opens the administrator login dialog.
        dialog = LoginDialog(self)

        if dialog.exec() == LoginDialog.DialogCode.Accepted:
            self.session_state = self.session_service.log_in(
                user_id=dialog.user_id,
                user_name=dialog.user_name,
                role=dialog.user_role,
            )
            self.mode_button.setText(self.session_state.button_label)
    
    def keyPressEvent(self, event):
        # End the application when the Escape key is pressed.
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
        else:
            # Keep the default behavior for other keys.
            super().keyPressEvent(event)


if __name__ == "__main__":
    # Start the Qt application
    app = QApplication(sys.argv)

    # Create the SAGE window and display it.
    window = SageWindow()
    window.show()

    # Keep the application running so it can respond to user input.
    sys.exit(app.exec())