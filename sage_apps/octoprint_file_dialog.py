"""Folder browser for the uploaded OctoPrint library."""

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from TouchControls.widgets import scroll_controls


class OctoPrintFileDialog(QDialog):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.folder = viewer.current_folder
        self.selected_file = None
        self.setWindowTitle("OctoPrint G-code Files")
        self.resize(700, 500)
        self.setStyleSheet(
            "QDialog { background-color: black; }"
            "QLabel, QLineEdit, QListWidget, QPushButton { color: white; font-size: 18px; }"
            "QLineEdit, QListWidget { background-color: black; border: 1px solid white; }"
            "QLineEdit, QPushButton { padding: 8px; }"
            "QPushButton { border: 1px solid white; border-radius: 6px; }"
            "QPushButton:disabled { color: gray; border-color: gray; }"
            "QListWidget::item { padding: 8px; }"
            "QListWidget::item:selected { background-color: #245a81; }"
        )
        layout = QVBoxLayout(self)
        navigation = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.go_back)
        navigation.addWidget(self.back_button)
        self.path_label = QLabel()
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.path_label.setWordWrap(True)
        navigation.addWidget(self.path_label, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(viewer.load_gcode_files)
        navigation.addWidget(self.refresh_button)
        layout.addLayout(navigation)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search this folder...")
        self.search_box.setAccessibleName("Search this folder")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self.populate)
        layout.addWidget(self.search_box)
        self.file_list = QListWidget()
        self.file_list.itemActivated.connect(self.open_selected)
        self.file_list.currentRowChanged.connect(self.update_open_button)
        layout.addWidget(self.file_list)
        layout.addWidget(scroll_controls(self.file_list))
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.open_selected)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        viewer.library_changed.connect(self.populate)
        viewer.library_status_changed.connect(self.show_status)
        self.populate()
        self.search_box.setFocus()

    def show_status(self, message):
        self.message_label.setText(message)
        loading = self.viewer.library_loading
        self.refresh_button.setEnabled(not loading)
        self.file_list.setEnabled(not loading)
        self.update_open_button()

    def populate(self):
        selected = self.file_list.currentItem()
        previous = selected.data(Qt.ItemDataRole.UserRole) if selected else self.viewer.selected_remote_file
        if self.folder not in self.viewer.remote_folders:
            self.folder = ""
        self.path_label.setText("/" + self.folder)
        self.back_button.setEnabled(bool(self.folder))
        self.file_list.clear()
        entries = self.viewer.remote_folders.get(self.folder, [])
        query = self.search_box.text().strip().casefold()
        for entry in entries:
            if query not in entry.name.casefold():
                continue
            item = QListWidgetItem(entry.name + ("/" if entry.is_folder else ""))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.file_list.addItem(item)
            if entry == previous:
                self.file_list.setCurrentItem(item)
        if self.file_list.currentRow() < 0 and self.file_list.count():
            self.file_list.setCurrentRow(0)
        empty = "No matching files or folders." if query else "This folder is empty."
        self.show_status(self.viewer.library_message or (empty if not self.file_list.count() else ""))

    def update_open_button(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(
            self.file_list.currentItem() is not None and not self.viewer.library_loading
            and not self.viewer.library_message)

    def open_selected(self, *_):
        item = self.file_list.currentItem()
        if item is None or self.viewer.library_loading or self.viewer.library_message:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry.is_folder:
            self.show_folder(entry.path)
        else:
            self.selected_file = entry
            self.accept()

    def go_back(self):
        self.show_folder(self.folder.rpartition("/")[0])

    def show_folder(self, path):
        self.folder = path
        # Clearing a search also emits textChanged; populate just once per move.
        with QSignalBlocker(self.search_box):
            self.search_box.clear()
        self.populate()
