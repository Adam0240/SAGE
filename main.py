import sys

from PySide6.QtWidgets import QApplication, QWidget


class SageWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SAGE")
        self.resize(1280, 720)
        self.setStyleSheet("background-color: black;")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = SageWindow()
    window.show()

    sys.exit(app.exec())