# Account management screen for logged-in SAGE staff.

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database.account_operations import (
    create_account,
    delete_account,
    list_accounts,
    update_account,
)


ROLE_LABELS = {
    "boss_admin": "Boss Admin",
    "steam_specialist": "STEAM Specialist",
    "base_specialist": "Work_Study Assistant",
}


class AccountWorker(QObject):
    completed = Signal(object)

    def __init__(self, actor_id, operation, **values):
        super().__init__()
        self.actor_id = actor_id
        self.operation = operation
        self.values = values

    @Slot()
    def run(self):
        # Run database work outside the Qt interface thread.
        try:
            if self.operation == "create":
                create_account(self.actor_id, **self.values)
                result = ("success", "Account created.")

            elif self.operation == "list":
                accounts = list_accounts(self.actor_id)
                result = ("success", accounts)

            elif self.operation == "update":
                update_account(self.actor_id, **self.values)
                result = ("success", "Account updated.")

            elif self.operation == "delete":
                delete_account(self.actor_id, **self.values)
                result = ("success", "Account deleted.")

            else:
                result = ("error", "Unknown account operation.")

        except PermissionError as error:
            result = ("error", str(error))
        except ValueError as error:
            result = ("error", str(error))
        except IntegrityError:
            result = ("error", "That username is already in use.")
        except SQLAlchemyError:
            result = ("error", "Database unavailable. Try again later.")
        except Exception:
            # Do not leave the screen waiting if an unexpected error occurs.
            result = ("error", "Could not complete the account operation.")

        self.completed.emit(result)


class AccountManagementDialog(QDialog):
    def __init__(self, actor_id: int, actor_role: str, parent=None):
        super().__init__(parent)

        self.actor_id = actor_id
        self.actor_role = actor_role
        self._accounts = {}
        self._thread = None
        self._result = None
        self._operation = None

        self.setWindowTitle("Account Management")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_create_tab()

        if actor_role in ("boss_admin", "steam_specialist"):
            self._build_manage_tab()


        self.status_label = QLabel("")
        self.status_label.setObjectName("account_status")
        layout.addWidget(self.status_label)

        self.setStyleSheet("""
            QDialog {
                background-color: black;
                color: white;
            }
            QLabel {
                color: white;
            }
            QLabel#account_status {
                color: #ff9999;
            }
            QLineEdit, QComboBox {
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
            QTabWidget::pane {
                border: 1px solid #777777;
            }
            QTabBar::tab {
                background-color: #222222;
                color: white;
                padding: 8px;
            }
            QTabBar::tab:selected {
                background-color: blue;
            }
        """)

        # Load existing accounts after the window has been constructed.
        if actor_role in ("boss_admin", "steam_specialist"):
            self._start_operation("list")

    def _build_create_tab(self):
        create_tab = QWidget()
        layout = QVBoxLayout(create_tab)
        form = QFormLayout()

        self.name_input = QLineEdit()
        form.addRow("Name:", self.name_input)

        self.username_input = QLineEdit()
        form.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password:", self.password_input)

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Confirm password:", self.confirm_input)

        self.role_input = QComboBox()

        # These choices help the user; AccountService checks permissions
        # against the current account in the database before creating one.
        if self.actor_role == "boss_admin":
            self.role_input.addItem("Boss Admin", "boss_admin")
            self.role_input.addItem("STEAM Specialist", "steam_specialist")

        if self.actor_role in ("boss_admin", "steam_specialist"):
            self.role_input.addItem(
                "Work_Study Assistant", "base_specialist"
            )

        form.addRow("Account role:", self.role_input)
        layout.addLayout(form)

        self.create_button = QPushButton("Create Account")
        self.create_button.clicked.connect(self.create_account)
        layout.addWidget(self.create_button)

        if self.actor_role == "boss_admin":
            # Make the least privileged new account the initial choice.
            self.role_input.setCurrentIndex(
                self.role_input.findData("base_specialist")
            )

        if self.actor_role == "base_specialist":
            self.create_button.setEnabled(False)
            layout.addWidget(QLabel(
                "Work_Study Assistants cannot create accounts."
            ))

        self.tabs.addTab(create_tab, "Create Account")

    def _build_manage_tab(self):
        manage_tab = QWidget()
        layout = QVBoxLayout(manage_tab)
        form = QFormLayout()

        self.account_input = QComboBox()
        self.account_input.currentIndexChanged.connect(
            self._selection_changed
        )
        form.addRow("Account:", self.account_input)

        self.edit_name_input = QLineEdit()
        form.addRow("Name:", self.edit_name_input)

        self.edit_username_input = QLineEdit()
        form.addRow("Username:", self.edit_username_input)

        self.edit_password_input = QLineEdit()
        self.edit_password_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.edit_password_input.setPlaceholderText(
            "Leave blank to keep the current password"
        )
        form.addRow("New password:", self.edit_password_input)

        self.edit_confirm_input = QLineEdit()
        self.edit_confirm_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        form.addRow("Confirm password:", self.edit_confirm_input)

        layout.addLayout(form)

        self.update_button = QPushButton("Save Changes")
        self.update_button.clicked.connect(self.save_changes)
        layout.addWidget(self.update_button)

        self.delete_button = QPushButton("Delete Selected Account")
        self.delete_button.clicked.connect(self.confirm_delete)
        layout.addWidget(self.delete_button)

        self.update_button.setEnabled(False)
        self.delete_button.setEnabled(False)

        self.tabs.addTab(manage_tab, "Manage Existing Accounts")

    def _selected_account(self):
        # The dropdown stores each account's database ID.
        return self._accounts.get(self.account_input.currentData())

    def _selection_changed(self, _index):
        account = self._selected_account()

        if account is None:
            self.edit_name_input.clear()
            self.edit_username_input.clear()
        else:
            _id, name, username, _role, _active = account
            self.edit_name_input.setText(name)
            self.edit_username_input.setText(username)

        self.edit_password_input.clear()
        self.edit_confirm_input.clear()

        own_password_only = (
            self.actor_role == "steam_specialist"
            and account is not None
            and account[0] == self.actor_id
        )
        self.edit_name_input.setReadOnly(own_password_only)
        self.edit_username_input.setReadOnly(own_password_only)

        available = self._thread is None and account is not None
        self.update_button.setEnabled(available)

        # This screen is for deleting other users. AccountService also
        # checks the last-Boss-Admin rule before any deletion.
        self.delete_button.setEnabled(
            available and account[0] != self.actor_id
        )

    def _show_accounts(self, accounts):
        selected_id = self.account_input.currentData()
        self._accounts = {
            account[0]: account for account in accounts
        }

        self.account_input.blockSignals(True)
        self.account_input.clear()

        for account in accounts:
            user_id, name, username, role, is_active = account
            role_label = ROLE_LABELS.get(role, role)
            inactive_label = " (inactive)" if not is_active else ""

            self.account_input.addItem(
                f"{name} ({username}) — {role_label}{inactive_label}",
                user_id,
            )

        previous_index = self.account_input.findData(selected_id)
        self.account_input.setCurrentIndex(
            previous_index if previous_index >= 0 else 0
        )
        self.account_input.blockSignals(False)

        self._selection_changed(self.account_input.currentIndex())

    def _start_operation(self, operation, **values):
        # Allow only one database operation at a time.
        if self._thread is not None:
            return

        self._operation = operation
        self._result = None
        self.tabs.setEnabled(False)

        self._thread = QThread(self)
        self._worker = AccountWorker(
            self.actor_id, operation, **values
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.completed.connect(self._receive_result)
        self._worker.completed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finish_operation)
        self._thread.start()

    @Slot(object)
    def _receive_result(self, result):
        self._result = result

    @Slot()
    def _finish_operation(self):
        # Handle the result after the worker thread has stopped.
        operation = self._operation
        result = self._result

        self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self.tabs.setEnabled(True)

        if result is None:
            self.status_label.setText(
                "Could not complete the account operation."
            )
            return

        status, details = result

        if status == "error":
            self.status_label.setText(details)

            if operation == "list":
                # Prevent edits using an account list we could not refresh.
                self._show_accounts([])

            return

        if operation == "list":
            self._show_accounts(details)
            return

        self.status_label.setText(details)

        if operation == "create":
            self.name_input.clear()
            self.username_input.clear()
            self.password_input.clear()
            self.confirm_input.clear()

        if operation == "update":
            self.edit_password_input.clear()
            self.edit_confirm_input.clear()


        # Refresh the dropdown after an account is created or changed.
        if self.actor_role in ("boss_admin", "steam_specialist"):
            self._start_operation("list")

    def create_account(self):
        if self._thread is not None:
            return

        if self.password_input.text() != self.confirm_input.text():
            self.status_label.setText("Passwords do not match.")
            return

        self.status_label.clear()
        self._start_operation(
            "create",
            name=self.name_input.text(),
            username=self.username_input.text(),
            password=self.password_input.text(),
            role=self.role_input.currentData(),
        )

    def save_changes(self):
        account = self._selected_account()

        if account is None or self._thread is not None:
            return

        password = self.edit_password_input.text()

        if password != self.edit_confirm_input.text():
            self.status_label.setText("Passwords do not match.")
            return

        self.status_label.clear()
        if self.actor_role == "steam_specialist" and account[0] == self.actor_id:
            self._start_operation(
                "update",
                target_id=self.actor_id,
                password=password if password else None,
            )
            return
        self._start_operation(
            "update",
            target_id=account[0],
            name=self.edit_name_input.text(),
            username=self.edit_username_input.text(),
            password=password if password else None,
        )

    def confirm_delete(self):
        account = self._selected_account()

        if (
            account is None
            or account[0] == self.actor_id
            or self._thread is not None
        ):
            return

        _id, name, username, _role, _active = account

        answer = QMessageBox.question(
            self,
            "Delete Account",
            f"Delete {name} ({username})? This cannot be undone.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.status_label.clear()
            self._start_operation(
                "delete",
                target_id=account[0],
            )

    def reject(self):
        # Keep the dialog alive while a database worker is running.
        if self._thread is None:
            super().reject()

    def closeEvent(self, event):
        if self._thread is not None:
            event.ignore()
        else:
            super().closeEvent(event)
