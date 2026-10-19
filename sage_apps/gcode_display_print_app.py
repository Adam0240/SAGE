# Provides the base widget used to build the G-code display and printing app.
from PySide6.QtCore import Qt, Signal
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QDialog, QDialogButtonBox, QListWidget, QLineEdit
)
from PySide6.QtGui import (
    QKeySequence, QShortcut, QPixmap
)

# Keep direct script launches able to import the shared services package.
if __name__ == "__main__" and __package__ is None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.gcode_preview_service import (
    GcodePreviewService, NoPreviewableMovementError, UnreadableGcodeError,
)

# Folder containing the G-code files available for printing.
GCODE_DIR = Path(
    r"C:\Users\STEAM Room\OneDrive - Aiken Technical College\3dPrint_Gcodes"
)
THUMB_DIR = Path(__file__).resolve().parent / "thumbnails"

# Creates the screen where users will browse G-code files and start prints.
class GcodeDisplayPrintApp(QWidget):
    home_requested = Signal()

    def __init__(self, parent=None, *, gcode_dir=None, thumbnail_dir=None):
        # Set up the QWidget and connect it to a parent widget if one is provided.
        super().__init__(parent)

        # Use installation defaults unless the caller supplies different folders.
        self.gcode_dir = Path(gcode_dir) if gcode_dir is not None else GCODE_DIR
        cache_dir = thumbnail_dir if thumbnail_dir is not None else THUMB_DIR
        self.preview_service = GcodePreviewService(cache_dir)

        # Set the title shown when the app is opened as a separate window.
        self.setWindowTitle("SAGE - 3D Printing")

        # Set the starting window size to match the main SAGE window.
        self.resize(1280, 720)

        # Use a black background to match the SAGE interface.
        self.setStyleSheet("background-color: black;")

        # Arrange the title and preview vertically inside the app window.
        self.main_layout = QVBoxLayout(self)

        # Leave space around the edges and between the title and preview.
        self.main_layout.setContentsMargins(40, 20, 40, 20)
        self.main_layout.setSpacing(20)

        # Arrange the Home button and title across the top of the app.
        self.header_layout = QHBoxLayout()

        # Create the button that will return to the main SAGE screen.
        self.home_button = QPushButton("Home")
        self.home_button.clicked.connect(self.close)
        self.home_button.setFixedSize(80, 80)
        self.home_button.setStyleSheet(
            "color: white;"
            "font-size: 18px;"
            "border: 2px solid white;"
            "border-radius: 40px;"
        )

        # Display the app title in the center of the header.
        self.title_label = QLabel("SAGE GCode Viewer")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            "color: white; font-size: 28px; font-weight: bold;"
        )

        # Reserve the same width on the right as the Home button on the left.
        # This keeps the title centered within the window.
        self.header_spacer = QWidget()
        self.header_spacer.setFixedWidth(80)

        # Give the title the available space between the two sides.
        self.header_layout.addWidget(self.home_button)
        self.header_layout.addWidget(self.title_label, stretch=1)
        self.header_layout.addWidget(self.header_spacer)

        # Place the header above the preview area.
        self.main_layout.addLayout(self.header_layout)

        # Reserve an area for the G-code preview.
        self.preview_label = QLabel("G-code Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet(
            "color: white;"
            "font-size: 22px;"
            "border: 2px solid white;"
        )

        # Give the preview the extra vertical space as the window grows.
        self.main_layout.addWidget(self.preview_label, stretch=1)

        # Arrange the previous button, filename, and next button in one row.
        self.file_navigation_layout = QHBoxLayout()
        self.file_navigation_layout.setSpacing(15)

        # Create the button that will display the previous G-code file.
        self.previous_button = QPushButton("<")
        self.previous_button.setFixedSize(60, 50)

        # Show a placeholder until the G-code files have been loaded.
        # Allow long filenames to wrap so they fit between the buttons.
        self.filename_label = QLabel("No file selected")
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename_label.setWordWrap(True)
        self.filename_label.setMinimumWidth(0)
        self.filename_label.setStyleSheet(
            "color: white; font-size: 20px;"
        )

        # Create the button that will display the next G-code file.
        self.next_button = QPushButton(">")
        self.next_button.setFixedSize(60, 50)

        # Give both navigation buttons the same appearance.
        for button in (self.previous_button, self.next_button):
            button.setStyleSheet(
                "color: white;"
                "font-size: 28px;"
                "border: 2px solid white;"
                "border-radius: 8px;"
            )

        # Keep the row centered and give the filename most of its width.
        self.file_navigation_layout.addStretch()
        self.file_navigation_layout.addWidget(self.previous_button)
        self.file_navigation_layout.addWidget(self.filename_label, stretch=1)
        self.file_navigation_layout.addWidget(self.next_button)
        self.file_navigation_layout.addStretch()

        # Place the navigation row directly beneath the preview.
        self.main_layout.addLayout(self.file_navigation_layout)

        # Create the button that will open the list of available G-code files.
        self.file_list_button = QPushButton("View File List")
        self.file_list_button.setFixedSize(180, 50)
        self.file_list_button.setStyleSheet(
            "color: white;"
            "font-size: 18px;"
            "border: 2px solid white;"
            "border-radius: 8px;"
        )

        # Center the file-list button beneath the filename and arrows.
        self.main_layout.addWidget(
            self.file_list_button,
            alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # Create the button that will send the selected file to OctoPrint.
        # Keep it disabled until the printing functionality is connected.
        self.start_print_button = QPushButton("Start Print")
        self.start_print_button.setFixedSize(300, 55)
        self.start_print_button.setEnabled(False)
        self.start_print_button.setStyleSheet(
            "QPushButton {"
            "    color: white;"
            "    font-size: 22px;"
            "    border: 2px solid white;"
            "    border-radius: 8px;"
            "}"
            "QPushButton:disabled {"
            "    color: gray;"
            "    border-color: gray;"
            "}"
        )

        # Center the print button at the bottom of the layout.
        self.main_layout.addWidget(
            self.start_print_button,
            alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # Store the available files and track which one is selected.
        self.gcode_files = []
        self.current_file_index = 0

        # Find the G-code files after the interface has been created.
        self.load_gcode_files()

        # Move backward or forward through the files when an arrow is clicked.
        self.previous_button.clicked.connect(self.show_previous_file)
        self.next_button.clicked.connect(self.show_next_file)
        self.file_list_button.clicked.connect(self.show_file_list)
        self.file_list_button.setEnabled(bool(self.gcode_files))

        # Navigation is only needed when more than one file is available.
        self.previous_button.setEnabled(len(self.gcode_files) > 1)
        self.next_button.setEnabled(len(self.gcode_files) > 1)

        # Use the left arrow key to select the previous file.
        self.previous_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Left), self
        )
        self.previous_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.previous_shortcut.activated.connect(self.show_previous_file)

        # Use the right arrow key to select the next file.
        self.next_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Right), self
        )
        self.next_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.next_shortcut.activated.connect(self.show_next_file)

        # Match keyboard navigation to the availability of the arrow buttons.
        self.previous_shortcut.setEnabled(len(self.gcode_files) > 1)
        self.next_shortcut.setEnabled(len(self.gcode_files) > 1)

    # Return to the owning home screen before this window closes.
    def closeEvent(self, event):
        self.home_requested.emit()
        super().closeEvent(event)

    # Find the G-code files and show the first filename in the interface.
    def load_gcode_files(self):
        try:
            # Check that the configured path points to an existing folder.
            if not self.gcode_dir.is_dir():
                self.filename_label.setText("G-code folder not found")
                self.preview_label.setText("Check the G-code folder path.")
                return

            # Include only G-code files and sort them alphabetically.
            # Converting the extension to lowercase also includes .GCODE files.
            self.gcode_files = sorted(
                (
                    path for path in self.gcode_dir.iterdir()
                    if path.is_file() and path.suffix.lower() == ".gcode"
                ),
                key=lambda path: path.name.lower()
            )

        except OSError:
            # Show a message if the folder cannot be accessed.
            self.filename_label.setText("Unable to access G-code folder")
            self.preview_label.setText("Check folder access and try again.")
            return

        # Show an empty-folder message if no G-code files were found.
        if not self.gcode_files:
            self.filename_label.setText("No G-code files found")
            self.preview_label.setText("Add G-code files to the selected folder.")
            return

        # Select the first file and display its name without the folder path.
        self.current_file_index = 0
        # Use the same display update for startup and arrow navigation.
        self.update_selected_file()

    # Select a file from the same ordered list used by the navigation arrows.
    def show_file_list(self):
        if not self.gcode_files:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Select G-code File")
        dialog.resize(600, 400)
        dialog.setStyleSheet(
            "QDialog { background-color: black; }"
            "QLineEdit { color: white; font-size: 18px; padding: 8px;"
            " border: 1px solid white; selection-background-color: #245a81; }"
            "QLabel { color: white; font-size: 18px; }"
            "QListWidget { color: white; font-size: 18px; border: 1px solid white; }"
            "QListWidget::item { padding: 8px; }"
            "QListWidget::item:selected { background-color: #245a81; color: white; }"
            "QPushButton { color: white; font-size: 18px; padding: 8px 20px;"
            " border: 1px solid white; border-radius: 6px; }"
        )
        layout = QVBoxLayout(dialog)
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search G-code filenames...")
        search_box.setAccessibleName("Search G-code filenames")
        search_box.setClearButtonEnabled(True)
        layout.addWidget(search_box)

        file_list = QListWidget()
        file_list.addItems([path.name for path in self.gcode_files])
        file_list.setCurrentRow(self.current_file_index)
        file_list.scrollToItem(file_list.currentItem())
        layout.addWidget(file_list)
        no_matches_label = QLabel("No matching G-code files.")
        no_matches_label.setObjectName("no_matches_label")
        no_matches_label.hide()
        layout.addWidget(no_matches_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        file_list.itemActivated.connect(dialog.accept)
        layout.addWidget(buttons)

        # Hide unmatched items so list rows still map to the original file indices.
        def filter_files(text):
            query = text.strip().casefold()
            first_match = -1
            for row in range(file_list.count()):
                item = file_list.item(row)
                matches = query in item.text().casefold()
                item.setHidden(not matches)
                if matches and first_match == -1:
                    first_match = row
            current = file_list.currentItem()
            if current is None or current.isHidden():
                file_list.setCurrentRow(first_match)
            no_matches_label.setVisible(first_match == -1)
            buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(first_match != -1)

        search_box.textChanged.connect(filter_files)
        search_box.setFocus()

        # Leave the current preview untouched until the user confirms a selection.
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_index = file_list.currentRow()
            selected_item = file_list.currentItem()
            if (0 <= selected_index < len(self.gcode_files)
                    and selected_item is not None and not selected_item.isHidden()):
                self.current_file_index = selected_index
                self.update_selected_file()
        dialog.deleteLater()

    # Display the previous file, wrapping to the last file from the first.
    def show_previous_file(self):
        # Avoid changing the selection when no files are available.
        if not self.gcode_files:
            return

        # The remainder operator keeps the index within the available files.
        self.current_file_index = (
            self.current_file_index - 1
        ) % len(self.gcode_files)

        self.update_selected_file()

    # Display the next file, wrapping to the first file from the last.
    def show_next_file(self):
        if not self.gcode_files:
            return

        self.current_file_index = (
            self.current_file_index + 1
        ) % len(self.gcode_files)

        self.update_selected_file()

    # Keep the displayed filename matched to the selected file.
    # Update the filename and preview together when the selection changes.
    def update_selected_file(self):
        selected_file = self.gcode_files[self.current_file_index]
        self.filename_label.setText(selected_file.name)
        self.display_gcode_preview(selected_file)

    # Translate preview outcomes into the image or message shown to the user.
    def display_gcode_preview(self, file_path):
        self.preview_label.clear()
        try:
            image = self.preview_service.get_preview(file_path)
        except UnreadableGcodeError:
            self.preview_label.setText("Unable to read this G-code file.")
        except NoPreviewableMovementError:
            self.preview_label.setText("No previewable movement found.")
        else:
            self.show_preview_image(image)

    # Fit either a saved or newly generated image into the preview area.
    def show_preview_image(self, image):
        preview = QPixmap.fromImage(image).scaled(
            self.preview_label.contentsRect().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(preview)

# Open the app for testing when this file is run directly.
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    # Create the Qt application that handles window events and user input.
    app = QApplication(sys.argv)

    # Create and display the G-code app window.
    window = GcodeDisplayPrintApp()
    window.show()

    # Keep the application running until the window is closed.
    # Return its exit code so the system knows how the application ended.
    sys.exit(app.exec())
