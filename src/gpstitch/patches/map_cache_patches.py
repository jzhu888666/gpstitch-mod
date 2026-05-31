"""Patch gopro_overlay map cache directory from GPStitch configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def patch_map_renderer_cache_dir() -> None:
    """Force MapRenderer to use GPStitch's project-local map cache when configured."""
    from gopro_overlay.geo import MapRenderer, MapStyler

    if getattr(MapRenderer, "_gpstitch_cache_patched", False):
        _patch_osm_https(MapStyler)
        return

    original_init = MapRenderer.__init__

    def __init__(self, cache_dir, styler):
        configured = os.environ.get("GPSTITCH_MAP_CACHE_DIR")
        if configured:
            cache_dir = Path(configured)
            cache_dir.mkdir(parents=True, exist_ok=True)
        original_init(self, cache_dir, styler)

    MapRenderer.__init__ = __init__
    MapRenderer._gpstitch_cache_patched = True
    _patch_osm_https(MapStyler)
    logger.debug("Patched MapRenderer cache directory")


def _patch_osm_https(MapStyler) -> None:
    """Prefer HTTPS for OpenStreetMap tiles so cache warmup avoids blocked HTTP."""
    if getattr(MapStyler, "_gpstitch_osm_https_patched", False):
        return

    original_provide = MapStyler.provide

    def provide(self, style: str = "osm"):
        attrs, key = original_provide(self, style)
        attrs = dict(attrs)
        url = attrs.get("url")
        if isinstance(url, str) and "tile.openstreetmap.org" in url and url.startswith("http://"):
            attrs["url"] = "https://" + url[len("http://") :]
        return attrs, key

    MapStyler.provide = provide
    MapStyler._gpstitch_osm_https_patched = True
