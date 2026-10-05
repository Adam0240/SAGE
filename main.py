# SAGE Main UI

import sys
from PySide6.QtCore import Qt
from login_dialog import LoginDialog
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

        # No administrator is logged in when SAGE starts.
        self.current_user_id = None
        self.current_user_name = None
        self.current_user_role = None

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
        self.mode_button = QPushButton("Student Mode")
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
        # A logged-in administrator can return to Student Mode.
        if self.current_user_id is not None:
            self.current_user_id = None
            self.current_user_name = None
            self.current_user_role = None
            self.mode_button.setText("Student Mode")
            return

        # Student Mode opens the administrator login dialog.
        dialog = LoginDialog(self)

        if dialog.exec() == LoginDialog.DialogCode.Accepted:
            self.current_user_id = dialog.user_id
            self.current_user_name = dialog.user_name
            self.current_user_role = dialog.user_role

            role_labels = {
                "boss_admin": "Admin Mode",
                "steam_specialist": "STEAM Specialist",
                "base_specialist": "Base Specialist",
            }
            self.mode_button.setText(
                role_labels[self.current_user_role]
            )
    
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