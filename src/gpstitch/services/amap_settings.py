"""AMap JS API credential and provider helpers."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from gpstitch.config import settings
from gpstitch.models.schemas import AMapRuntimeConfigResponse, AMapSettingsResponse

AMAP_MAP_STYLE = "amap-jsapi"
AMAP_SATELLITE_MAP_STYLE = "amap-jsapi-satellite"
AMAP_MIXED_MAP_STYLE = "amap-jsapi-mixed"
AMAP_MAP_STYLES = frozenset({AMAP_MAP_STYLE, AMAP_SATELLITE_MAP_STYLE, AMAP_MIXED_MAP_STYLE, "amap"})
AMAP_PROVIDER = "amap"
AMAP_JSAPI_VERSION = "2.0"
AMAP_FALLBACK_STYLE = "osm"
AMAP_STANDARD_LAYER = "standard"
AMAP_SATELLITE_ROADNET_LAYER = "satellite-roadnet"
AMAP_JOURNEY_WIDGET_TYPES = frozenset({"journey_map", "moving_journey_map"})


def is_amap_style(map_style: str | None) -> bool:
    """Return true when a map style is backed by AMap JSAPI."""
    return (map_style or "").lower() in AMAP_MAP_STYLES


def normalize_amap_style(map_style: str | None) -> str:
    """Return a supported AMap style id."""
    style = (map_style or "").lower()
    if style == AMAP_SATELLITE_MAP_STYLE:
        return AMAP_SATELLITE_MAP_STYLE
    if style == AMAP_MIXED_MAP_STYLE:
        return AMAP_MIXED_MAP_STYLE
    return AMAP_MAP_STYLE


def amap_layer_type(map_style: str | None) -> str:
    """Return the browser layer type for an AMap style id."""
    if normalize_amap_style(map_style) == AMAP_SATELLITE_MAP_STYLE:
        return AMAP_SATELLITE_ROADNET_LAYER
    return AMAP_STANDARD_LAYER


def amap_layer_type_for_widget(map_style: str | None, widget_type: str | None = None) -> str:
    """Return the AMap layer type for a specific map widget."""
    normalized = normalize_amap_style(map_style)
    if normalized == AMAP_MIXED_MAP_STYLE:
        return AMAP_SATELLITE_ROADNET_LAYER if widget_type in AMAP_JOURNEY_WIDGET_TYPES else AMAP_STANDARD_LAYER
    return amap_layer_type(normalized)


def backend_map_style(map_style: str | None) -> str | None:
    """Map browser-only AMap style to a backend-renderable fallback."""
    if is_amap_style(map_style):
        return AMAP_FALLBACK_STYLE
    return map_style


def amap_fallback_message() -> str:
    return "AMap JSAPI is unavailable; GPStitch will use the configured non-AMap map path only when fallback is explicit."


class AMapSettingsService:
    """Persist AMap credentials locally and expose redacted metadata."""

    def __init__(self, settings_path: Path | None = None, legacy_settings_path: Path | None = None):
        self.settings_path = settings_path or settings.settings_dir / "amap.json"
        self.legacy_settings_path = (
            legacy_settings_path
            if legacy_settings_path is not None
            else (None if settings_path is not None else settings.legacy_settings_dir / "amap.json")
        )
        self._lock = RLock()

    def get_settings(self) -> AMapSettingsResponse:
        with self._lock:
            return self._to_response(self._read())

    def get_runtime_config(self) -> AMapRuntimeConfigResponse:
        with self._lock:
            data = self._read()
            configured = bool(data.get("key") and data.get("security_js_code"))
            return AMapRuntimeConfigResponse(
                configured=configured,
                validated=bool(data.get("validated")) if configured else False,
                key=data.get("key") if configured else None,
                security_js_code=data.get("security_js_code") if configured else None,
                key_fingerprint=self._fingerprint(data.get("key")) if configured else None,
            )

    def save_credentials(self, key: str, security_js_code: str) -> AMapSettingsResponse:
        key = key.strip()
        security_js_code = security_js_code.strip()
        if not key or not security_js_code:
            raise ValueError("AMap key and security JS code are required")

        with self._lock:
            existing = self._read()
            data = {
                "key": key,
                "security_js_code": security_js_code,
                "validated": False,
                "last_validated_at": None,
                "last_error": None,
                "validation_generation": int(existing.get("validation_generation", 0)) + 1,
            }
            written_path = self._write(data)
            if written_path != self.legacy_settings_path:
                self._remove_legacy()
            return self._to_response(data)

    def record_validation(self, success: bool, error: str | None = None) -> AMapSettingsResponse:
        with self._lock:
            data = self._read()
            if not data.get("key") or not data.get("security_js_code"):
                raise ValueError("AMap credentials are not configured")
            data["validated"] = bool(success)
            data["last_validated_at"] = datetime.now(UTC).isoformat()
            data["last_error"] = None if success else self._sanitize_error(error, data)
            if not success:
                data["validation_generation"] = int(data.get("validation_generation", 0)) + 1
            written_path = self._write(data)
            if written_path != self.legacy_settings_path:
                self._remove_legacy()
            return self._to_response(data)

    def clear(self) -> AMapSettingsResponse:
        with self._lock:
            if self.settings_path.exists():
                self.settings_path.unlink()
            self._remove_legacy()
            return AMapSettingsResponse()

    def cache_fingerprint(self) -> str:
        with self._lock:
            data = self._read()
            configured = bool(data.get("key") and data.get("security_js_code"))
            if not configured:
                return "unconfigured"
            raw = f"{data.get('key', '')}\0{data.get('security_js_code', '')}\0{data.get('validation_generation', 0)}"
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _read(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            migrated = self._read_legacy()
            if migrated:
                written_path = self._write(migrated)
                if written_path != self.legacy_settings_path:
                    self._remove_legacy()
                return migrated
            return {}
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict[str, Any]) -> Path:
        try:
            return self._write_to_path(self.settings_path, data)
        except OSError:
            if self.legacy_settings_path is None or self.legacy_settings_path == self.settings_path:
                raise
            self.settings_path = self.legacy_settings_path
            return self._write_to_path(self.settings_path, data)

    def _write_to_path(self, path: Path, data: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)
        temp_path.replace(path)
        return path

    def _read_legacy(self) -> dict[str, Any]:
        if self.legacy_settings_path is None or not self.legacy_settings_path.exists():
            return {}
        try:
            data = json.loads(self.legacy_settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _remove_legacy(self) -> None:
        if self.legacy_settings_path is None:
            return
        try:
            self.legacy_settings_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _to_response(self, data: dict[str, Any]) -> AMapSettingsResponse:
        configured = bool(data.get("key") and data.get("security_js_code"))
        return AMapSettingsResponse(
            configured=configured,
            validated=bool(data.get("validated")) if configured else False,
            key_fingerprint=self._fingerprint(data.get("key")) if configured else None,
            last_validated_at=data.get("last_validated_at") if configured else None,
            last_error=data.get("last_error") if configured else None,
            validation_generation=int(data.get("validation_generation", 0)) if configured else 0,
        )

    def _fingerprint(self, key: str | None) -> str | None:
        if not key:
            return None
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def _sanitize_error(self, error: str | None, data: dict[str, Any]) -> str:
        message = (error or "AMap validation failed").strip()
        for secret in (data.get("key"), data.get("security_js_code")):
            if secret:
                message = message.replace(str(secret), "[redacted]")
        message = re.sub(r"key=([^&\s]+)", "key=[redacted]", message, flags=re.IGNORECASE)
        return message[:500]


amap_settings_service = AMapSettingsService()
