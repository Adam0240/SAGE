import pytest

from services.octoprint_file_service import parse_library


@pytest.mark.parametrize("name", ["..", "../file.gcode", "a\\b.gcode"])
def test_invalid_paths_are_rejected(name):
    with pytest.raises(ValueError):
        parse_library({"files": [dict(name=name, type="machinecode")]})
