"""Camera asset locations without importing the vision libraries."""

from pathlib import Path

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"
