from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch


def test_manual_probe_import_does_not_contact_ollama():
    path = Path(__file__).resolve().parents[2] / "manual_ollama_probe.py"
    spec = spec_from_file_location("manual_probe_test", path)
    with patch("ollama.Client") as client:
        spec.loader.exec_module(module_from_spec(spec))
        client.assert_not_called()
