# Assign category markers from the test directory so tests can be selected with pytest -m.

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def qt_app():
    # Import Qt only for tests that use it; retain one widget-capable owner.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    yield app


@pytest.fixture(autouse=True)
def _ensure_widget_application(request):
    relative = Path(request.node.path).relative_to(Path(__file__).parent)
    if relative.parts[0] == "ui":
        request.getfixturevalue("qt_app")

REQUIRED_TEST_MODULES = {
    "unit/test_manual_diagnostics.py",
    "ui/test_home_voice.py",
    "unit/test_voice_command_service.py",
    "unit/test_project_search_service.py",
    "unit/test_print_remaining_time.py",
    "unit/test_disk_cache.py",
    "unit/test_supervised_speech_service.py",
    "unit/test_setup_admin.py",
    "unit/test_octoprint_library.py",
    "integration/test_setup_admin_concurrency.py",
    "unit/test_speech_recognition_service.py",
    "unit/test_account_service.py",
    "unit/test_authentication_service.py",
    "unit/test_password_service.py",
    "unit/test_database_configuration.py",
    "unit/test_gcode_parser.py",
    "unit/test_guide_services.py",
    "unit/test_camera_manager.py",
    "unit/test_calibration.py",
    "unit/test_dwell.py",
    "unit/test_ai_assistant_service.py",
    "unit/test_text_to_speech_service.py",
    "ui/test_home_camera_input.py",
    "ui/test_hand_calibration.py",
    "ui/test_main_window.py",
    "ui/test_gcodedisplayapp.py",
    "ui/test_octoprint_files.py",
    "ui/test_gcode_preview_service.py",
    "ui/test_account_dialog.py",
    "ui/test_login_dialog.py",
    "ui/test_configuration_startup.py",
    "ui/test_steamguide_app.py",
    "integration/test_account_transactions.py",
    "integration/test_boss_admin_concurrency.py",
}


def pytest_addoption(parser):
    parser.addoption(
        "--check-collection", action="store_true",
        help="Require collected tests from every expected SAGE test module (used by CI).",
    )


def pytest_collection_finish(session):
    if session.config.getoption("--check-collection"):
        test_root = Path(__file__).resolve().parent
        collected = {Path(item.path).relative_to(test_root).as_posix() for item in session.items}
        missing = REQUIRED_TEST_MODULES - collected
        if missing:
            raise pytest.UsageError("Required test modules not collected: " + ", ".join(sorted(missing)))


def pytest_collection_modifyitems(items):
    test_root = Path(__file__).resolve().parent
    for item in items:
        category = Path(item.path).relative_to(test_root).parts[0]
        if category in ("unit", "ui", "integration"):
            item.add_marker(getattr(pytest.mark, category))
