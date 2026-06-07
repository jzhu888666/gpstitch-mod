"""Runtime settings persisted from the UI."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from gpstitch.config import settings


def _clamp_render_concurrency(value: Any, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(1, min(3, parsed))


class RuntimeSettingsService:
    """Persist user-adjustable runtime settings."""

    def __init__(self, settings_path: Path | None = None):
        self.settings_path = settings_path or settings.settings_dir / "runtime.json"
        self._lock = RLock()

    def get_render_concurrency(self, default: int = 1) -> int:
        """Return persisted render concurrency, falling back to the configured default."""
        with self._lock:
            data = self._read()
            return _clamp_render_concurrency(data.get("render_concurrency"), default)

    def set_render_concurrency(self, value: int) -> int:
        """Persist render concurrency and return the clamped value."""
        concurrency = _clamp_render_concurrency(value)
        with self._lock:
            data = self._read()
            data["render_concurrency"] = concurrency
            data["updated_at"] = datetime.now(UTC).isoformat()
            self._write(data)
            return concurrency

    def get_shutdown_after_all_tasks(self, default: bool = False) -> bool:
        """Return whether shutdown should be scheduled after the render queue drains."""
        with self._lock:
            data = self._read()
            value = data.get("shutdown_after_all_tasks", default)
            return bool(value)

    def set_shutdown_after_all_tasks(self, enabled: bool) -> bool:
        """Persist the global task-manager shutdown switch."""
        enabled = bool(enabled)
        with self._lock:
            data = self._read()
            data["shutdown_after_all_tasks"] = enabled
            data["updated_at"] = datetime.now(UTC).isoformat()
            self._write(data)
            return enabled

    def _read(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return {}
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.settings_path.parent,
            prefix=f".{self.settings_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)
        temp_path.replace(self.settings_path)


runtime_settings_service = RuntimeSettingsService()
