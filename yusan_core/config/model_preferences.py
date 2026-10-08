"""Persistence for non-secret LLM presentation preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path


class ModelPreferences:
    """Persist the selected model without placing credentials in a config file."""

    def __init__(self, path: Path | None = None) -> None:
        configured_path = os.environ.get("YUSAN_CONFIG_PATH")
        self._path = path or (Path(configured_path) if configured_path else Path.home() / ".yusan" / "settings.json")

    def selected_model(self) -> str | None:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8")).get("gemini_model")
        except (OSError, ValueError, TypeError):
            return None
        return value.strip() if isinstance(value, str) and value.strip() else None

    def save_selected_model(self, model: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps({"gemini_model": model}, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(self._path)
