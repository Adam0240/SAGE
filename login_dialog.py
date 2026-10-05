# Login dialog for SAGE administrator accounts.

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from sqlalchemy.exc import SQLAlchemyError

from database.connection import SessionLocal
from database.user_repository import UserRepository
from services.authentication_service import AuthenticationService
from services.password_service import PasswordService


class LoginWorker(QObject):
    # The result is either account details, None, or a database error.
    completed = Signal(object)

    def __init__(self, username: str, password: str):
        super().__init__()
        self.username = username
        self.password = password

    @Slot()
    def run(self):
        try:
            # Create and use the database session in this worker thread.
            with SessionLocal() as session:
                authentication = AuthenticationService(
                    UserRepository(session),
                    PasswordService(),
                )
                user = authentication.authenticate(
                    self.username,
                    self.password,
                )

                if user is None:
                    self.completed.emit(("invalid", None))
                    return

                # Copy account values before closing the database session.
                details = (user.id, user.name, user.role)
                self.completed.emit(("success", details))

        except SQLAlchemyError:
            self.completed.emit(("database_error", None))


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("SAGE Login")
        self.setMinimumWidth(350)

        self.user_id = None
        self.user_name = None
        self.user_role = None

        self._thread = None
        self._result = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setObjectName("username_input")
        form.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setObjectName("password_input")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password:", self.password_input)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff7777;")
        layout.addWidget(self.error_label)

        self.login_button = QPushButton("Log In")
        self.login_button.clicked.connect(self.attempt_login)
        layout.addWidget(self.login_button)

        self.password_input.returnPressed.connect(self.attempt_login)

        self.setStyleSheet("""
            QDialog {
                background-color: black;
                color: white;
            }
            QLabel {
                color: white;
            }
            QLineEdit {
                background-color: #222222;
                color: white;
                border: 1px solid #777777;
                padding: 6px;
            }
            QPushButton {
                background-color: blue;
                color: white;
                padding: 8px;
            }
        """)

    def attempt_login(self):
        # Prevent repeated clicks from starting simultaneous login attempts.
        if self._thread is not None:
            return

        self.error_label.setText("")
        self.login_button.setEnabled(False)
        self.login_button.setText("Connecting...")

        self._result = None
        self._thread = QThread(self)
        self._worker = LoginWorker(
            self.username_input.text(),
            self.password_input.text(),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.completed.connect(self._receive_result)
        self._worker.completed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finish_attempt)
        self._thread.start()

    @Slot(object)
    def _receive_result(self, result):
        self._result = result

    @Slot()
    def _finish_attempt(self):
        # This runs after the worker thread has stopped.
        status, details = self._result

        self._thread.deleteLater()
        self._thread = None
        self._worker = None

        self.login_button.setEnabled(True)
        self.login_button.setText("Log In")

        if status == "success":
            self.user_id, self.user_name, self.user_role = details
            self.accept()
        elif status == "database_error":
            self.error_label.setText(
                "Database unavailable. Try again later."
            )
            self.password_input.clear()
        else:
            self.error_label.setText("Invalid username or password.")
            self.password_input.clear()

    def reject(self):
        # Keep the dialog alive until an active worker has stopped.
        if self._thread is None:
            super().reject()