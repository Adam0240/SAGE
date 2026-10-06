# Assign category markers from the test directory so tests can be selected with pytest -m.

from pathlib import Path

import pytest


REQUIRED_TEST_MODULES = {
    "unit/test_account_service.py",
    "unit/test_authentication_service.py",
    "unit/test_password_service.py",
    "unit/test_database_configuration.py",
    "ui/test_main_window.py",
    "ui/test_account_dialog.py",
    "ui/test_login_dialog.py",
    "ui/test_configuration_startup.py",
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
