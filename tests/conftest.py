# Assign category markers from the test directory so tests can be selected with pytest -m.

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items):
    test_root = Path(__file__).resolve().parent
    for item in items:
        category = Path(item.path).relative_to(test_root).parts[0]
        if category in ("unit", "ui", "integration"):
            item.add_marker(getattr(pytest.mark, category))
