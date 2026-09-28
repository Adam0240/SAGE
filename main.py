# SAGE Main UI

import sys
from PySide6.QtWidgets import QApplication, QWidget


class SageWindow(QWidget):
    def __init__(self):
        # Set up the QWidget before adding the SAGE window settings.
        super().__init__()

        # Set the window title, starting size, and background color.
        self.setWindowTitle("SAGE")
        self.resize(1280, 720)
        self.setStyleSheet("background-color: black;")


if __name__ == "__main__":
    # Start the Qt application
    app = QApplication(sys.argv)

    # Create the SAGE window and display it.
    window = SageWindow()
    window.show()

    # Keep the application running so it can respond to user input.
    sys.exit(app.exec())