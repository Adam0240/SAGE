import pytest
import os
import subprocess
import sys
from pathlib import Path
from threading import Event, current_thread, get_ident
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QTextBrowser

from sage_apps.steamguide_app import SteamGuide_App
from main import SageWindow
from services.ai_response_worker import AIResponseLoader
from services.guide_response_service import GuideResponse
from shiboken6 import isValid


def wait_until(predicate, timeout=3):
    deadline = monotonic() + timeout
    while not predicate() and monotonic() < deadline:
        QApplication.processEvents()
        QTest.qWait(5)
    assert predicate(), "Timed out waiting for asynchronous response"


def wait_for_response(window):
    wait_until(lambda: not window.ai_loader.busy and window.ask_button.isEnabled())


@pytest.fixture(autouse=True)
def offline_client():
    # Exercise real retrieval and worker threads without contacting Ollama.
    with patch("services.ai_assistant_service.Client") as client:
        client.return_value.chat.side_effect = ConnectionError("Offline test")
        yield client.return_value


@pytest.fixture
def guide(tmp_path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "printer.md").write_text(
        "# Printer\n## Filament jam\nStop the job and ask staff.", encoding="utf-8")
    window = SteamGuide_App(tutorial_directory=tmp_path)
    window.show()
    app.processEvents()
    yield window
    if isValid(window):
        window.close()
        wait_until(lambda: not window.ai_loader.busy)
        window.deleteLater()
    app.processEvents()


def test_enter_displays_instructions_and_source_then_clears_stale_source(guide):
    guide.question_input.setText("filament jam")
    QTest.keyClick(guide.question_input, Qt.Key.Key_Return)
    wait_for_response(guide)
    assert "Stop the job and ask staff." in guide.response_display.toPlainText()
    assert guide.source_label.text() == "Sources used: printer.md → Filament jam"
    guide.question_input.setText("spaceship repair")
    guide.submit_question()
    wait_for_response(guide)
    assert "couldn't find a clear answer" in guide.response_display.toPlainText()
    assert guide.source_label.text() == "Sources used: None"


def test_blank_question_preserves_response_and_reference_list_refreshes(guide):
    guide.question_input.setText("filament jam")
    guide.submit_question()
    wait_for_response(guide)
    previous = guide.response_display.toPlainText()
    guide.question_input.setText("  ")
    guide.submit_question()
    assert guide.response_display.toPlainText() == previous
    (guide.tutorial_directory / "laser.md").write_text(
        "# Laser\n## Dark engraving\nAsk staff to check settings.", encoding="utf-8")
    guide.question_input.setText("dark engraving")
    guide.submit_question()
    wait_for_response(guide)
    assert "laser.md" in guide.source_label.text()
    assert guide.reference_layout.count() == 2


@pytest.fixture
def blocked_answer(offline_client):
    started, release = Event(), Event()
    worker_threads = []
    threads = []

    def respond(**kwargs):
        worker_threads.append(get_ident())
        threads.append(current_thread())
        started.set()
        if not release.wait(5):
            raise TimeoutError("Test did not release the worker")
        return SimpleNamespace(message=SimpleNamespace(content="Generated answer"))

    offline_client.chat.side_effect = respond
    yield started, release, worker_threads
    release.set()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive(), "Mock worker did not finish"


def test_slow_answer_keeps_ui_responsive_and_prevents_duplicate_requests(
        guide, blocked_answer, offline_client):
    started, release, worker_threads = blocked_answer
    guide.question_input.setText("filament jam")
    guide.ask_button.click()
    try:
        wait_until(started.is_set)
        assert worker_threads[0] != get_ident()
        assert guide.response_display.toPlainText() == "SAGE is thinking..."
        assert not guide.ask_button.isEnabled()
        assert not guide.question_input.isEnabled()
        assert guide.home_button.isEnabled()
        request = guide._ai_request
        guide.submit_question()
        assert guide._ai_request == request
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        wait_until(lambda: bool(ticks))
        assert guide.ai_loader.busy
    finally:
        release.set()
        wait_for_response(guide)
    assert offline_client.chat.call_count == 1
    assert "Generated answer" in guide.response_display.toPlainText()
    assert guide.question_input.isEnabled()
    assert "printer.md" in guide.source_label.text()


@pytest.mark.parametrize("action", ["home", "hide"])
def test_leaving_during_generation_discards_answer(guide, blocked_answer, action):
    started, release, _ = blocked_answer
    guide.question_input.setText("filament jam")
    guide.submit_question()
    old_thread = guide.ai_loader.thread
    try:
        wait_until(started.is_set)
        if action == "home":
            guide.home_button.click()
        else:
            guide.hide()
        assert not guide.isVisible()
        assert guide.ask_button.isEnabled()
        assert guide.question_input.isEnabled()
        assert not guide.ai_loader.busy
        assert old_thread.is_alive()
        previous = guide.response_display.toPlainText()
    finally:
        release.set()
        wait_until(lambda: not old_thread.is_alive())
    assert guide.response_display.toPlainText() == previous
    assert guide.source_label.text() == "Sources used: None"
    guide.show()
    guide.submit_question()
    wait_for_response(guide)
    assert "Generated answer" in guide.response_display.toPlainText()


@pytest.mark.parametrize("old_finishes_first", [False, True])
def test_home_reopen_submits_without_waiting_and_rejects_stale_answers(
        guide, offline_client, old_finishes_first):
    started = [Event(), Event()]
    release = [Event(), Event()]
    threads = []

    def respond(**kwargs):
        index = len(threads)
        threads.append(current_thread())
        started[index].set()
        if not release[index].wait(10):
            raise TimeoutError("Test did not release the worker")
        return SimpleNamespace(message=SimpleNamespace(
            content="Old answer" if index == 0 else "New answer"))

    offline_client.chat.side_effect = respond
    window = SageWindow(camera_controls=False)
    try:
        window.show()
        with patch("main.SteamGuide_App", side_effect=lambda parent: SteamGuide_App(
                parent=parent, tutorial_directory=guide.tutorial_directory)):
            window.app_buttons[2].click()
        assistant = window.steamguide_window
        assistant.question_input.setText("filament jam")
        assistant.submit_question()
        wait_until(started[0].is_set)
        old_request = assistant._ai_request
        assistant.home_button.click()
        assert window.isVisible() and not assistant.isVisible()
        assert not assistant.ai_loader.busy
        window.app_buttons[2].click()
        assert window.steamguide_window is assistant
        assistant.question_input.setText("How do I fix a filament jam?")
        assistant.ask_button.click()
        wait_until(started[1].is_set)
        assert threads[0].is_alive()
        assert assistant._ai_request != old_request
        assistant.submit_question()
        assert offline_client.chat.call_count == 2

        # Simulate a result queued just before cancellation as well as a late
        # signal delivery. Neither may change the active request's UI.
        assistant.ai_loader.results.put((old_request, GuideResponse("Stale answer")))
        assistant.ai_loader._poll()
        assistant._ai_response_completed(old_request, GuideResponse("Stale answer"))
        assert assistant.response_display.toPlainText() == "SAGE is thinking..."
        assert not assistant.ask_button.isEnabled()
        if old_finishes_first:
            release[0].set()
            wait_until(lambda: not threads[0].is_alive())
            assert assistant.response_display.toPlainText() == "SAGE is thinking..."
        release[1].set()
        wait_for_response(assistant)
        assert "New answer" in assistant.response_display.toPlainText()
        assert "printer.md" in assistant.source_label.text()
        release[0].set()
        wait_until(lambda: not threads[0].is_alive())
        assistant.ai_loader._poll()
        assert "Old answer" not in assistant.response_display.toPlainText()
        assert "New answer" in assistant.response_display.toPlainText()
        assert offline_client.chat.call_count == 2
    finally:
        for event in release:
            event.set()
        for thread in threads:
            thread.join(timeout=3)
            assert not thread.is_alive()
        window.close()
        window.deleteLater()


def test_destroying_guide_during_request_never_delivers_to_deleted_qt_objects(
        guide, blocked_answer):
    started, release, _ = blocked_answer
    received = []
    loader = guide.ai_loader
    loader.completed.connect(lambda *args: received.append(args))
    guide.question_input.setText("filament jam")
    guide.submit_question()
    thread = loader.thread
    wait_until(started.is_set)
    # deleteLater bypasses closeEvent/hideEvent cancellation.
    guide.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(guide)
    assert not isValid(loader)
    assert loader.shutdown.is_set()
    assert thread.is_alive()
    release.set()
    wait_until(lambda: not thread.is_alive())
    QApplication.processEvents()
    assert loader.results.empty()
    assert received == []


@pytest.mark.parametrize("destroy", [False, True])
def test_launcher_shutdown_during_request(guide, blocked_answer, destroy):
    started, release, _ = blocked_answer
    window = SageWindow(camera_controls=False)
    try:
        window.show()
        with patch("main.SteamGuide_App", side_effect=lambda parent: SteamGuide_App(
                parent=parent, tutorial_directory=guide.tutorial_directory)):
            window.app_buttons[2].click()
        assistant = window.steamguide_window
        loader = assistant.ai_loader
        received = []
        loader.completed.connect(lambda *args: received.append(args))
        assistant.question_input.setText("filament jam")
        assistant.submit_question()
        thread = loader.thread
        wait_until(started.is_set)
        if destroy:
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert not isValid(loader)
            assert loader.shutdown.is_set()
        else:
            window.close()
            assert not window.isVisible() and not assistant.isVisible()
            assert not loader.busy
        assert thread.is_alive()
        release.set()
        wait_until(lambda: not thread.is_alive())
        assert loader.results.empty()
        assert received == []
    finally:
        release.set()
        if isValid(window):
            window.close()
            window.deleteLater()


def test_standalone_startup_without_repository_on_python_path(tmp_path):
    script = Path(__file__).resolve().parents[2] / "sage_apps" / "steamguide_app.py"
    # Execute the script's actual __main__ block in a fresh interpreter, with
    # script-launch globals and no repository root supplied by pytest/PYTHONPATH.
    bootstrap = """
import sys
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
script = Path(sys.argv[1])
sys.path.insert(0, str(script.parent))
original_exec = QApplication.exec
def run_loop(app):
    QTimer.singleShot(0, app.quit)
    return original_exec()
scope = {"__name__": "__main__", "__file__": str(script), "__package__": None}
with patch.object(QApplication, "exec", run_loop):
    exec(compile(script.read_bytes(), str(script), "exec"), scope)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", bootstrap, str(script)],
        cwd=tmp_path, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_loader_only_delivers_latest_pending_answer(guide, blocked_answer, offline_client):
    started, release, _ = blocked_answer
    loader = AIResponseLoader(guide)
    received = []
    loader.completed.connect(lambda request, response: received.append(
        (request, response, get_ident())))
    loader.submit("filament jam", guide.tutorial_directory)
    try:
        wait_until(started.is_set)
        skipped = loader.submit("filament jam", guide.tutorial_directory)
        latest = loader.submit("filament jam", guide.tutorial_directory)
        # Also cover stale results already queued before cancellation.
        loader.results.put((skipped, GuideResponse("Stale answer")))
    finally:
        release.set()
        wait_until(lambda: not loader.busy)
    assert offline_client.chat.call_count == 2
    assert len(received) == 1
    assert received[0][0] == latest
    assert "Generated answer" in received[0][1].markdown
    assert received[0][2] == get_ident()
    assert not loader.timer.isActive()


@pytest.mark.parametrize("failure", ["setup", "response", "retrieval"])
def test_worker_failures_restore_controls(guide, failure):
    target = ("services.ai_response_worker.DocumentRetrievalService"
              if failure == "retrieval" else
              "services.ai_response_worker.AIAssistantService")
    with patch(target) as service:
        if failure == "response":
            service.return_value.respond.side_effect = RuntimeError("Test failure")
        else:
            service.side_effect = RuntimeError("Test failure")
        guide.question_input.setText("filament jam")
        guide.submit_question()
        wait_for_response(guide)
    assert guide.question_input.isEnabled()
    if failure == "retrieval":
        assert "documentation is unavailable" in guide.response_display.toPlainText()
        assert guide.source_label.text() == "Sources used: None"
    else:
        assert "Stop the job and ask staff." in guide.response_display.toPlainText()
        assert "printer.md" in guide.source_label.text()


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
        wait_for_response(assistant)
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
