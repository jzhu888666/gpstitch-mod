"""Configuration settings for GPStitch."""

import contextlib
import os
import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_settings_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "GPStitch" / "settings"
    return Path.home() / ".gpstitch" / "settings"


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="GPSTITCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # Local mode - work with local file paths instead of uploading (default: enabled)
    # Set GPSTITCH_LOCAL_MODE=false to disable and use file upload mode
    local_mode: bool = True

    # Runtime patching for gopro_overlay library
    # Set GPSTITCH_ENABLE_GOPRO_PATCHES=false to disable patches
    enable_gopro_patches: bool = True

    # Use wrapper script for gopro-dashboard.py (enables patches in subprocess)
    # Set GPSTITCH_USE_WRAPPER_SCRIPT=false to use original script
    use_wrapper_script: bool = True

    # File storage settings
    temp_dir: Path = Path(tempfile.gettempdir()) / "gpstitch"
    file_ttl_seconds: int = 3600  # 1 hour
    max_upload_size_bytes: int = 2 * 1024 * 1024 * 1024  # 2GB

    # Project-local cache directories
    cache_dir: Path = PROJECT_ROOT / ".gpstitch-cache"
    map_cache_dir: Path = PROJECT_ROOT / ".gpstitch-cache" / "maps"
    layout_cache_dir: Path = PROJECT_ROOT / ".gpstitch-cache" / "layouts"
    legacy_settings_dir: Path = PROJECT_ROOT / ".gpstitch-cache" / "settings"
    settings_dir: Path = _default_settings_dir()
    map_cache_warmup_max_tiles: int = 2048
    # Keep render startup responsive. Frontend/background warmup can prefetch
    # many tiles, while render itself should not block on network tile fetches.
    map_cache_render_warmup_max_tiles: int = 0

    # Template storage directory
    templates_dir: Path = Path.home() / ".gpstitch" / "templates"

    # Allowed file extensions
    allowed_extensions: set[str] = {".mp4", ".mov", ".gpx", ".fit", ".srt"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.map_cache_dir.mkdir(parents=True, exist_ok=True)
        self.layout_cache_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_settings_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self.settings_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
