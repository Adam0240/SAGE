# Login dialog for SAGE administrator accounts.

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


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("SAGE Login")
        self.setMinimumWidth(350)

        # These values are filled in only after a successful login.
        self.user_id = None
        self.user_name = None
        self.user_role = None

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

        login_button = QPushButton("Log In")
        login_button.clicked.connect(self.attempt_login)
        layout.addWidget(login_button)

        # Pressing Enter in the password field also attempts login.
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
        username = self.username_input.text()
        password = self.password_input.text()

        try:
            with SessionLocal() as session:
                repository = UserRepository(session)
                authentication = AuthenticationService(
                    repository,
                    PasswordService(),
                )
                user = authentication.authenticate(username, password)

                if user is not None:
                    # Copy the values before the database session closes.
                    self.user_id = user.id
                    self.user_name = user.name
                    self.user_role = user.role

        except SQLAlchemyError:
            self.error_label.setText(
                "Database unavailable. Try again later."
            )
            self.password_input.clear()
            return

        if self.user_id is None:
            self.error_label.setText("Invalid username or password.")
            self.password_input.clear()
            return

        self.accept()