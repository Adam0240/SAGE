import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStyle,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.ai_response_worker import AIResponseLoader

# Keep standalone launches able to import the shared services.
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.document_retrieval_service import DocumentRetrievalService
from services.guide_response_service import GuideResponseService
from TouchControls.widgets import scroll_controls


class SteamGuide_App(QWidget):
    home_requested = Signal()

    def __init__(self, parent=None, *, tutorial_directory=None):
        super().__init__(parent)
        self.setProperty("sageTouchWindow", True)

        self.setWindowTitle("SAGE - STEAM Assistant")
        self.resize(1280, 720)

        # Locate the documentation relative to the project folder.
        self.tutorial_directory = (
            Path(tutorial_directory) if tutorial_directory is not None
            else Path(__file__).resolve().parent.parent / "STEAM_Tutorials"
        )
        self.retrieval_service = DocumentRetrievalService(self.tutorial_directory)
        self.response_service = GuideResponseService()

        # Handle AI responses without blocking the interface.
        self.ai_loader = AIResponseLoader(self)
        self.ai_loader.completed.connect(self._ai_response_completed)
        self._ai_request = 0

        self.build_layout()
        self.load_reference_files()

    def build_layout(self):
        # Create the main layout.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 25, 40, 30)
        main_layout.setSpacing(20)

        # Create the question field.
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Type your question")
        self.question_input.setAccessibleName("Ask the STEAM assistant")
        self.question_input.setMinimumHeight(55)
        self.question_input.setMaximumWidth(750)
        self.question_input.returnPressed.connect(self.submit_question)

        # Balance the Home button so the question stays centered.
        header_layout = QHBoxLayout()
        self.home_button = QPushButton("Home")
        self.home_button.setObjectName("homeButton")
        self.home_button.setFixedSize(80, 80)
        self.home_button.clicked.connect(self.close)
        header_layout.addWidget(self.home_button)
        header_layout.addStretch()
        header_layout.addWidget(
            self.question_input,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        header_layout.addStretch()
        self.ask_button = QPushButton("Ask SAGE")
        self.ask_button.setMinimumSize(130, 55)
        self.ask_button.clicked.connect(self.submit_question)
        header_layout.addWidget(self.ask_button)
        main_layout.addLayout(header_layout)

        # Create the outer panel containing the response and references.
        content_panel = QFrame()
        content_panel.setObjectName("contentPanel")

        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(25, 25, 25, 20)
        content_layout.setSpacing(25)

        # Create the response area.
        self.response_display = QTextBrowser()
        self.response_display.setObjectName("responseDisplay")
        self.response_display.setPlaceholderText(
            "Your answer will appear here."
        )
        self.response_display.setMinimumSize(320, 250)
        self.response_display.setMaximumWidth(600)

        content_layout.addWidget(
            self.response_display,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        content_layout.addWidget(scroll_controls(self.response_display))

        # Identify the actual document sections used by the current response.
        self.source_label = QLabel("Sources used: None")
        self.source_label.setObjectName("sourceLabel")
        self.source_label.setWordWrap(True)

        content_layout.addWidget(self.source_label)
        reference_heading = QLabel("Reference documents")
        reference_heading.setObjectName("referenceHeading")
        content_layout.addWidget(reference_heading)

        # Create a scrollable row of reference icons.
        reference_scroll = QScrollArea()
        reference_scroll.setWidgetResizable(True)
        reference_scroll.setFrameShape(QFrame.Shape.NoFrame)
        reference_scroll.setMinimumHeight(190)
        reference_scroll.setMaximumHeight(210)

        reference_container = QWidget()
        self.reference_layout = QHBoxLayout(reference_container)
        self.reference_layout.setContentsMargins(10, 10, 10, 10)
        self.reference_layout.setSpacing(25)

        reference_scroll.setWidget(reference_container)
        content_layout.addWidget(reference_scroll)
        content_layout.addWidget(scroll_controls(reference_scroll, horizontal=True))

        main_layout.addWidget(content_panel, stretch=1)

        # Match the black, white, and blue styling of the other SAGE apps.
        # Child document dialogs inherit these rules as well.
        self.setStyleSheet("""
            QWidget {
                background-color: black;
                color: white;
                font-size: 18px;
            }

            QLineEdit,
            QTextBrowser,
            QFrame#contentPanel {
                border: 2px solid white;
                border-radius: 8px;
            }

            QLineEdit,
            QTextBrowser {
                padding: 12px;
                selection-background-color: #245a81;
                selection-color: white;
            }

            QLineEdit {
                background-color: #222222;
                placeholder-text-color: #bbbbbb;
            }

            QLineEdit:focus,
            QTextBrowser:focus {
                border-color: #336699;
            }

            QLabel#sourceLabel {
                color: #bbbbbb;
                font-size: 16px;
            }

            QLabel#referenceHeading {
                font-size: 20px;
                font-weight: bold;
            }

            QToolButton {
                border: 2px solid white;
                border-radius: 8px;
                padding: 10px;
            }

            QPushButton {
                border: 2px solid white;
                border-radius: 8px;
                padding: 8px;
            }

            QPushButton:disabled {
                color: #777777;
                border-color: #777777;
            }

            QPushButton#homeButton {
                border: 2px solid white;
                border-radius: 40px;
            }

            QPushButton#homeButton:hover,
            QPushButton#homeButton:focus {
                background-color: #222222;
                border-color: #336699;
            }

            QToolButton:hover {
                background-color: #222222;
                border-color: #336699;
            }

            QToolButton:focus {
                border-color: #336699;
            }

            QToolButton:pressed {
                background-color: #245a81;
            }

            QToolTip {
                background-color: #222222;
                color: white;
                border: 1px solid #777777;
                padding: 6px;
            }
        """)

    def closeEvent(self, event):
    # Ignore pending AI responses when returning Home.
        self.ai_loader.cancel()

        self.ask_button.setEnabled(True)
        self.question_input.setEnabled(True)

        self.home_requested.emit()
        super().closeEvent(event)

    def hideEvent(self, event):
    # Discard responses if the guide is hidden during generation.
        self.ai_loader.cancel()
        self.ask_button.setEnabled(True)
        self.question_input.setEnabled(True)
        super().hideEvent(event)

    def load_reference_files(self):
        # Rebuild from the current index so added and removed files stay in sync.
        while self.reference_layout.count():
            item = self.reference_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        reference_files = self.retrieval_service.files

        if not reference_files:
            self.reference_layout.addWidget(
                QLabel("No Markdown reference files found.")
            )
            return

        for file_path in reference_files:
            # Create a document icon for this file.
            button = QToolButton()
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setIcon(
                self.style().standardIcon(
                    QStyle.StandardPixmap.SP_FileIcon
                )
            )
            button.setIconSize(QSize(55, 65))
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            )
            button.setText(file_path.stem.replace("_", "\n"))
            button.setToolTip(file_path.name)
            button.setMinimumSize(160, 145)

            # Capture this file's path for its button.
            button.clicked.connect(
                lambda checked=False, path=file_path:
                self.open_reference(path)
            )

            self.reference_layout.addWidget(
                button,
                alignment=Qt.AlignmentFlag.AlignCenter,
            )

    def submit_question(self):
        question = self.question_input.text().strip()

        if not question or self.ai_loader.busy:
            return

        # Display feedback while the AI processes the question.
        self.response_display.setPlainText("SAGE is thinking...")
        self.source_label.setText("Sources used: None")
        self.ask_button.setEnabled(False)
        self.question_input.setEnabled(False)

        # Submit the question to the background worker.
        self._ai_request = self.ai_loader.submit(
            question,
            self.tutorial_directory,
        )


    def _ai_response_completed(self, request_id, response):
        # Ignore outdated results.
        if request_id != self._ai_request:
            return

        self.response_display.setMarkdown(response.markdown)
        self.source_label.setText(
            "Sources used: " + ("; ".join(response.sources) or "None")
        )

        self.ask_button.setEnabled(True)
        self.question_input.setEnabled(True)

        # Refresh the reference document list.
        self.retrieval_service.refresh()
        self.load_reference_files()

    def open_reference(self, file_path):
        # Open the selected document in a read-only window.
        dialog = QDialog(self)
        dialog.setWindowTitle(file_path.name)
        dialog.resize(750, 600)

        layout = QVBoxLayout(dialog)

        document_viewer = QTextBrowser()
        layout.addWidget(document_viewer)
        layout.addWidget(scroll_controls(document_viewer))
        close_button = QPushButton("Close")
        close_button.setMinimumHeight(44)
        close_button.clicked.connect(dialog.reject)
        layout.addWidget(close_button)

        try:
            contents = file_path.read_text(encoding="utf-8")

            if contents.strip():
                document_viewer.setMarkdown(contents)
            else:
                document_viewer.setPlainText(
                    "This reference document is currently empty."
                )

        except (OSError, UnicodeError) as error:
            document_viewer.setPlainText(
                f"Unable to open this reference document.\n\n{error}"
            )

        dialog.exec()
        dialog.deleteLater()


# Allow this application to run independently for testing.
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SteamGuide_App()
    window.show()
    sys.exit(app.exec())
