
"""Configuration for SAGE's local AI assistant."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class AIConfig:
    model: str
    host: str
    timeout: float


def load_ai_config() -> AIConfig:
    # Load settings from the project .env file.
    env_path = Path(__file__).resolve().parents[1] / ".env"
    settings = dotenv_values(env_path)

    def get_setting(name, default):
        return os.environ.get(name, settings.get(name) or default)

    timeout = float(get_setting("SAGE_OLLAMA_TIMEOUT", "60"))

    if not 1 <= timeout <= 120:
        raise ValueError("AI timeout must be between 1 and 120 seconds.")

    return AIConfig(
        model=get_setting("SAGE_OLLAMA_MODEL", "qwen3:1.7b"),
        host=get_setting("SAGE_OLLAMA_HOST", "http://127.0.0.1:11434"),
        timeout=timeout,
    )
