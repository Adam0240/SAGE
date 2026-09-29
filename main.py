# SAGE Main UI

import sys
from PySide6.QtCore import Qt
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

        # Set the window title, starting size, and background color.
        self.setWindowTitle("SAGE")
        self.resize(1280, 720)
        self.setStyleSheet("background-color: black;")

        # Arrange the main parts of the screen from top to bottom.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 40)
        main_layout.setSpacing(0)

        # Display the application name at the top of the screen.
        title = QLabel("STEAM Artificial Guidance Expert")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 36px; font-weight: bold;")
        main_layout.addWidget(title)

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
                    background-color: green;
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


if __name__ == "__main__":
    # Start the Qt application
    app = QApplication(sys.argv)

    # Create the SAGE window and display it.
    window = SageWindow()
    window.show()

    # Keep the application running so it can respond to user input.
    sys.exit(app.exec())