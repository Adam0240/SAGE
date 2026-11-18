"""Home voice controls with audio, AI, and playback isolated."""

from types import SimpleNamespace
from threading import Thread
from unittest.mock import Mock, patch

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from main import SageWindow
from services.home_voice_controller import HomeSpeechRecognitionService, HomeVoiceController


@pytest.fixture
def voice():
    app = QApplication.instance() or QApplication([])
    with patch("services.home_voice_controller.HomeSpeechRecognitionService") as speech_type, patch(
        "services.home_voice_controller.TextToSpeechService"
    ) as tts_type, patch("services.home_voice_controller.AIResponseLoader") as ai_type:
        speech = speech_type.return_value
        speech.start_recording.return_value = True
        tts = tts_type.return_value
        tts.is_speaking.return_value = False
        tts.speak.return_value = True
        ai_type.return_value.submit.return_value = 7
        window = SageWindow(camera_controls=False)
        window.show()
        yield SimpleNamespace(window=window, speech=speech, tts=tts,
                              ai=ai_type.return_value, app=app)
        window.close()
        window.deleteLater()
        app.processEvents()


def assert_button(window, text, enabled):
    assert window.talk_button.text() == text
    assert window.talk_button.accessibleName() == text
    assert window.talk_button.isEnabled() == enabled


def start(voice):
    voice.window.talk_button.click()
    return voice.speech.start_recording.call_args.kwargs


@pytest.mark.parametrize("manual_stop", [True, False])
def test_voice_cycle(voice, manual_stop):
    w = voice.window
    assert_button(w, "Talk to SAGE", True)
    callbacks = start(voice)
    assert_button(w, "Starting microphone...", False)
    w.talk_button.click()
    voice.speech.start_recording.assert_called_once()
    voice.speech.stop_recording.assert_not_called()
    callbacks["on_ready"]()
    assert_button(w, "Listening...", True)
    if manual_stop:
        w.talk_button.click()
        voice.speech.stop_recording.assert_called_once()
    else:
        voice.speech.on_captured()
    assert_button(w, "Transcribing...", False)
    callbacks["on_ready"]()  # A late readiness signal must not re-enable recording.
    assert_button(w, "Transcribing...", False)
    callbacks["on_result"]("  Help with filament  ")
    voice.ai.submit.assert_called_once_with("Help with filament", w.voice_controller.tutorial_directory)
    assert_button(w, "SAGE is thinking...", False)
    assert w.voice_controller.thinking_timer.isActive()
    w.voice_controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="Answer", markdown="Answer"))
    voice.tts.speak.assert_called_once_with("Answer")
    assert_button(w, "Talk to SAGE", True)
    assert w.voice_controller.thinking_timer.isActive()
    w.voice_controller.on_tts_state_changed("ready")
    assert not w.voice_controller.thinking_timer.isActive()
    assert_button(w, "Talk to SAGE", True)


@pytest.mark.parametrize("speaking", [False, True])
def test_interrupt_waits_350_ms_and_cancel_prevents_restart(voice, speaking):
    w = voice.window
    voice.tts.is_speaking.return_value = speaking
    w.voice_controller.start_thinking_animation()
    w.voice_controller._awaiting_tts_completion = True
    w.talk_button.click()
    voice.tts.stop.assert_called_once()
    assert not w.voice_controller.thinking_timer.isActive()
    assert_button(w, "Starting microphone...", False)
    voice.speech.start_recording.assert_not_called()
    assert w.voice_controller._tts_handoff_timer.isActive()
    assert w.voice_controller._tts_handoff_timer.interval() == 350
    w.voice_controller.on_tts_state_changed("ready")
    assert_button(w, "Starting microphone...", False)
    voice.tts.is_speaking.return_value = False
    w.voice_controller._tts_handoff_timer.stop()
    w.voice_controller.start_speech_after_tts()
    callbacks = voice.speech.start_recording.call_args.kwargs
    assert_button(w, "Starting microphone...", False)
    callbacks["on_ready"]()
    assert_button(w, "Listening...", True)
    w.voice_controller.cancel()
    callbacks["on_ready"]()
    callbacks["on_result"]("stale")
    assert_button(w, "Talk to SAGE", True)
    voice.ai.submit.assert_not_called()
    voice.tts.is_speaking.return_value = True
    w.talk_button.click()
    w.close()
    assert not w.voice_controller._tts_handoff_timer.isActive()
    w.voice_controller.start_speech_after_tts()
    assert voice.speech.start_recording.call_count == 1
    assert not w.voice_controller.thinking_timer.isActive()


@pytest.mark.parametrize("failure", ["empty", "callback", "start", "busy", "ai", "tts"])
def test_failures_restore_idle_and_show_errors(voice, failure):
    w = voice.window
    if failure == "start":
        voice.speech.start_recording.side_effect = RuntimeError("No microphone")
    elif failure == "busy":
        voice.speech.start_recording.return_value = False
    callbacks = start(voice)
    if failure == "empty":
        callbacks["on_result"](" ")
    elif failure == "callback":
        callbacks["on_error"]("Whisper failed")
    elif failure in ("ai", "tts"):
        if failure == "ai":
            voice.ai.submit.side_effect = RuntimeError("AI failed")
        callbacks["on_result"]("question")
        if failure == "tts":
            voice.tts.speak.return_value = False
            w.voice_controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="answer", markdown=""))
    assert_button(w, "Talk to SAGE", True)
    assert not w.voice_controller.thinking_timer.isActive()
    dialogs = w.findChildren(QMessageBox)
    assert bool(dialogs) == (failure != "empty")
    for dialog in dialogs:
        assert dialog.isVisible()
        dialog.accept()


@pytest.mark.parametrize("destination", ["open_gcode_app", "open_steamguide_app", "close"])
def test_navigation_cancels_and_ignores_late_callbacks(voice, destination):
    w = voice.window
    callbacks = start(voice)
    with patch("main.GcodeDisplayPrintApp"), patch("main.SteamGuide_App"):
        getattr(w, destination)()
    voice.speech.cancel_recording.assert_called()
    voice.ai.cancel.assert_called()
    voice.tts.stop.assert_called()
    callbacks["on_ready"]()
    callbacks["on_error"]("stale error")
    callbacks["on_result"]("stale transcript")
    voice.speech.on_captured()
    assert_button(w, "Talk to SAGE", destination != "close")
    assert not w.findChildren(QMessageBox)
    voice.ai.submit.assert_not_called()


def test_capture_adapter_reports_completion_before_transcription():
    service = HomeSpeechRecognitionService()
    service.on_captured = Mock()
    audio = object()
    with patch("services.home_voice_controller.SpeechRecognitionService._capture_audio", return_value=audio):
        assert service._capture_audio() is audio
    service.on_captured.assert_called_once_with()


@pytest.mark.parametrize("stage", ["thinking", "speaking"])
def test_cancel_stops_animation_and_ignores_late_answer(voice, stage):
    w = voice.window
    start(voice)["on_result"]("question")
    response = SimpleNamespace(spoken_text="answer", markdown="")
    if stage == "speaking":
        w.voice_controller.on_voice_ai_response(7, response)
    assert w.voice_controller.thinking_timer.isActive()
    w.voice_controller.cancel()
    voice.tts.speak.reset_mock()
    w.voice_controller.on_voice_ai_response(7, response)
    w.voice_controller.on_tts_state_changed("ready")
    voice.tts.speak.assert_not_called()
    assert not w.voice_controller.thinking_timer.isActive()
    assert_button(w, "Talk to SAGE", True)


def test_playback_error_restores_idle_and_displays_dialog(voice):
    w = voice.window
    start(voice)["on_result"]("question")
    w.voice_controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="answer", markdown=""))
    w.voice_controller.on_tts_state_changed("error")
    w.voice_controller.on_tts_error("Playback failed")
    assert_button(w, "Talk to SAGE", True)
    assert not w.voice_controller.thinking_timer.isActive()
    dialog = w.findChild(QMessageBox)
    assert dialog.text() == "Playback failed"
    assert dialog.isVisible()
    dialog.accept()


@pytest.mark.parametrize("stage", ["initializing", "listening", "transcribing",
                                   "thinking", "speaking", "handoff"])
@pytest.mark.parametrize("logout", [False, True])
def test_mode_change_cancels_voice_in_every_stage(voice, stage, logout):
    w = voice.window
    callbacks = start(voice)
    if stage in ("listening", "transcribing"):
        callbacks["on_ready"]()
    if stage == "transcribing":
        w.talk_button.click()
    if stage in ("thinking", "speaking", "handoff"):
        callbacks["on_result"]("question")
    if stage in ("speaking", "handoff"):
        w.voice_controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="answer", markdown=""))
    if stage == "handoff":
        w.talk_button.click()
        assert w.voice_controller._tts_handoff_timer.isActive()
    if logout:
        w.session_state = w.session_service.log_in(7, "Staff", "boss_admin")
    with patch("main.LoginDialog") as login:
        login.DialogCode.Accepted = QDialog.DialogCode.Accepted
        login.return_value.exec.return_value = QDialog.DialogCode.Rejected

        def check_cancelled():
            assert not w.voice_controller._speech_busy
            assert not w.voice_controller._awaiting_tts_completion
            assert not w.voice_controller.thinking_timer.isActive()
            assert not w.voice_controller._tts_handoff_timer.isActive()
            return QDialog.DialogCode.Rejected

        login.return_value.exec.side_effect = check_cancelled
        w.handle_mode_button()
        assert login.return_value.exec.call_count == (0 if logout else 1)
    voice.speech.cancel_recording.assert_called()
    voice.ai.cancel.assert_called()
    voice.tts.stop.assert_called()
    voice.ai.submit.reset_mock()
    callbacks["on_ready"]()
    callbacks["on_result"]("late question")
    callbacks["on_error"]("late error")
    w.voice_controller.on_tts_state_changed("ready")
    w.voice_controller.on_tts_error("late playback error")
    w.voice_controller.start_speech_after_tts()
    voice.ai.submit.assert_not_called()
    assert not w.findChildren(QMessageBox)
    assert not w.voice_controller._tts_handoff_timer.isActive()
    assert_button(w, "Talk to SAGE", True)


@pytest.mark.parametrize("destination", ["open_gcode_app", "open_steamguide_app", "close"])
def test_late_tts_errors_are_ignored_after_navigation(voice, destination):
    w = voice.window
    start(voice)["on_result"]("question")
    w.voice_controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="answer", markdown=""))
    with patch("main.GcodeDisplayPrintApp"), patch("main.SteamGuide_App"):
        getattr(w, destination)()
    w.voice_controller.on_tts_error("late error")
    w.voice_controller.on_tts_state_changed("ready")
    assert not w.findChildren(QMessageBox)
    if destination != "close":
        w.show_home()
        start(voice)
        w.voice_controller.on_tts_error("old playback error during new capture")
        w.voice_controller.on_tts_state_changed("ready")
        assert_button(w, "Starting microphone...", False)
        assert not w.findChildren(QMessageBox)


def test_deferred_shutdown_blocks_voice_and_navigation(voice):
    w = voice.window
    camera = Mock()
    camera.worker = object()
    w.camera_controller = camera
    w.voice_controller._awaiting_tts_completion = True
    w.talk_button.click()
    assert w.voice_controller._tts_handoff_timer.isActive()
    assert not w.close()
    assert w.isVisible()
    assert not w.isEnabled()
    assert not w.voice_controller._tts_handoff_timer.isActive()
    w.talk_button.click()
    w.voice_controller.toggle_speech()
    w.voice_controller.start_speech_after_tts()
    w.voice_controller.on_tts_error("late error")
    voice.speech.start_recording.assert_not_called()
    with patch("main.LoginDialog") as login, patch("main.GcodeDisplayPrintApp") as gcode:
        w.handle_mode_button()
        w.open_gcode_app()
        login.assert_not_called()
        gcode.assert_not_called()
    assert not w.findChildren(QMessageBox)
    assert_button(w, "Talk to SAGE", False)
    camera.worker = None
    w.camera_stopped()
    assert not w.isVisible()


def test_cancelled_handoff_does_not_start_a_new_handoff_early(voice):
    w = voice.window
    w.voice_controller._awaiting_tts_completion = True
    w.talk_button.click()
    QTest.qWait(200)
    w.voice_controller.cancel()
    assert not w.voice_controller._tts_handoff_timer.isActive()
    w.voice_controller._awaiting_tts_completion = True
    w.talk_button.click()
    # Cross the original deadline while remaining before the replacement deadline.
    QTest.qWait(220)
    voice.speech.start_recording.assert_not_called()
    assert w.voice_controller._tts_handoff_timer.isActive()
    QTest.qWait(200)
    voice.speech.start_recording.assert_called_once()
    assert not w.voice_controller._tts_handoff_timer.isActive()
    assert_button(w, "Starting microphone...", False)


def test_queued_worker_readiness_is_rejected_after_cancellation(voice):
    w = voice.window
    callbacks = start(voice)
    worker = Thread(target=callbacks["on_ready"])
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert_button(w, "Starting microphone...", False)
    w.voice_controller.cancel()
    voice.app.processEvents()
    assert_button(w, "Talk to SAGE", True)


def test_repeated_playback_errors_show_only_one_dialog(voice):
    w = voice.window
    start(voice)["on_result"]("question")
    w.voice_controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="answer", markdown=""))
    w.voice_controller.on_tts_error("first error")
    w.voice_controller.on_tts_error("duplicate error")
    dialogs = w.findChildren(QMessageBox)
    assert len(dialogs) == 1
    assert dialogs[0].text() == "first error"
    dialogs[0].accept()


def test_avatar_signals_update_the_home_widget(voice):
    w = voice.window
    callbacks = start(voice)
    callbacks["on_result"]("question")
    assert w.avatar.text() == "●"
    w.voice_controller.advance_thinking_animation()
    assert w.avatar.text() == "●   ●"
    w.voice_controller.advance_thinking_animation()
    assert w.avatar.text() == "●   ●   ●"
    w.voice_controller.cancel()
    assert w.avatar.text() == "●   ●   ●"
    assert not w.voice_controller.thinking_timer.isActive()


def test_controller_operates_without_a_window(voice):
    controller = HomeVoiceController()
    states, errors, frames = [], [], []
    controller.button_changed.connect(lambda text, enabled: states.append((text, enabled)))
    controller.error_occurred.connect(errors.append)
    controller.avatar_changed.connect(frames.append)
    try:
        assert controller.parent() is None
        assert controller.thinking_timer.parent() is controller
        assert controller._tts_handoff_timer.parent() is controller
        assert controller.tutorial_directory.is_dir()
        controller.toggle_speech()
        assert states[-1] == ("Starting microphone...", False)
        callbacks = voice.speech.start_recording.call_args.kwargs
        callbacks["on_ready"]()
        assert states[-1] == ("Listening...", True)
        callbacks["on_result"]("question")
        assert states[-1] == ("SAGE is thinking...", False)
        assert frames[-1] == "●"
        controller.on_voice_ai_response(7, SimpleNamespace(spoken_text="answer", markdown=""))
        controller.on_tts_error("Playback failed")
        assert errors == ["Playback failed"]
        assert states[-1] == ("Talk to SAGE", True)
        assert frames[-1] == "●   ●   ●"
        controller.shutdown()
        assert states[-1] == ("Talk to SAGE", False)
        voice.speech.start_recording.reset_mock()
        controller.toggle_speech()
        voice.speech.start_recording.assert_not_called()
    finally:
        controller.shutdown()
        controller.deleteLater()
