import pytest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QTextBrowser

from sage_apps.steamguide_app import SteamGuide_App
from main import SageWindow


@pytest.fixture
def guide(tmp_path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "printer.md").write_text(
        "# Printer\n## Filament jam\nStop the job and ask staff.", encoding="utf-8")
    window = SteamGuide_App(tutorial_directory=tmp_path)
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    app.processEvents()


def test_enter_displays_instructions_and_source_then_clears_stale_source(guide):
    guide.question_input.setText("filament jam")
    QTest.keyClick(guide.question_input, Qt.Key.Key_Return)
    assert "Stop the job and ask staff." in guide.response_display.toPlainText()
    assert guide.source_label.text() == "Sources used: printer.md → Filament jam"
    guide.question_input.setText("spaceship repair")
    guide.submit_question()
    assert "couldn't find a clear answer" in guide.response_display.toPlainText()
    assert guide.source_label.text() == "Sources used: None"


def test_blank_question_preserves_response_and_reference_list_refreshes(guide):
    guide.question_input.setText("filament jam")
    guide.submit_question()
    previous = guide.response_display.toPlainText()
    guide.question_input.setText("  ")
    guide.submit_question()
    assert guide.response_display.toPlainText() == previous
    (guide.tutorial_directory / "laser.md").write_text(
        "# Laser\n## Dark engraving\nAsk staff to check settings.", encoding="utf-8")
    guide.question_input.setText("dark engraving")
    guide.submit_question()
    assert "laser.md" in guide.source_label.text()
    assert guide.reference_layout.count() == 2


@pytest.mark.parametrize("kind, expected", [
    ("normal", "Stop the job and ask staff."),
    ("empty", "currently empty"),
    ("missing", "Unable to open this reference document"),
    ("unreadable", "Unable to open this reference document"),
    ("invalid_encoding", "Unable to open this reference document"),
])
def test_reference_viewer_handles_documents_and_read_failures(guide, kind, expected):
    path = guide.tutorial_directory / "printer.md"
    if kind == "empty":
        path.write_text("", encoding="utf-8")
    elif kind == "missing":
        path.unlink()
    elif kind == "invalid_encoding":
        path.write_bytes(b"\xff")
    captured = []

    def inspect(dialog):
        captured.append(dialog.findChild(QTextBrowser).toPlainText())
        return QDialog.DialogCode.Accepted

    with patch.object(QDialog, "exec", inspect):
        if kind == "unreadable":
            with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
                guide.open_reference(path)
        else:
            # Exercise the actual reference button's captured file path.
            guide.reference_layout.itemAt(0).widget().click()
    assert len(captured) == 1
    assert expected in captured[0]


@pytest.mark.parametrize("staff", [False, True])
def test_launcher_home_close_and_shutdown_preserve_guide_state(guide, staff):
    window = SageWindow(camera_controls=False)
    try:
        if staff:
            window.session_state = window.session_service.log_in(
                user_id=7, user_name="Staff User", role="boss_admin")
            window.mode_button.setText(window.session_state.button_label)
            window.app_buttons[0].setEnabled(True)
        session = window.session_state
        window.show()
        with patch("main.SteamGuide_App", side_effect=lambda parent: SteamGuide_App(
                parent=parent, tutorial_directory=guide.tutorial_directory)):
            window.app_buttons[2].click()
        assistant = window.steamguide_window
        assert assistant.isVisible() and not window.isVisible()
        assistant.question_input.setText("filament jam")
        assistant.submit_question()
        response = assistant.response_display.toPlainText()
        source = assistant.source_label.text()
        assistant.home_button.click()
        assert window.isVisible() and not assistant.isVisible()
        assert window.session_state is session
        assert window.app_buttons[0].isEnabled() == staff
        window.app_buttons[2].click()
        assert window.steamguide_window is assistant
        assert assistant.question_input.text() == "filament jam"
        assert assistant.response_display.toPlainText() == response
        assert assistant.source_label.text() == source
        assistant.close()
        assert window.isVisible() and not assistant.isVisible()
        assert window.session_state is session
        window.app_buttons[2].click()
        window.close()
        assert not window.isVisible() and not assistant.isVisible()
    finally:
        window.close()
        window.deleteLater()
