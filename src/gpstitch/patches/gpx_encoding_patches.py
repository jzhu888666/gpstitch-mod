"""Patch gopro_overlay GPX loading to avoid locale-dependent decoding."""

from __future__ import annotations

import gzip
import logging
from pathlib import Path

from gpstitch.patches.xml_encoding import decode_xml_bytes

logger = logging.getLogger(__name__)


def _decode_gpx_bytes(data: bytes) -> str:
    """Decode GPX XML bytes without relying on Windows' ANSI code page."""
    return decode_xml_bytes(data)


def patch_gpx_file_encoding() -> None:
    """Patch gopro_overlay.gpx.load so GPX files are decoded consistently.

    Upstream opens plain GPX files with ``Path.open("r")``. On Chinese Windows
    that means GBK, which fails for UTF-8 GPX files containing extension fields
    or non-ASCII metadata. Reading bytes first also keeps this patch independent
    of the process locale used by the preview server and render wrapper.
    """
    import gopro_overlay.gpx as gpx_module

    if getattr(gpx_module, "_gpstitch_gpx_encoding_patched", False):
        logger.debug("gopro_overlay.gpx.load already patched for GPX encoding")
        return

    original_load = gpx_module.load

    def patched_load(filepath: Path, units):
        path = Path(filepath)
        if path.suffix.lower() == ".gz":
            with gzip.open(path, "rb") as gpx_file:
                data = gpx_file.read()
        else:
            data = path.read_bytes()
        return gpx_module.load_xml(_decode_gpx_bytes(data), units)

    gpx_module._gpstitch_original_load = original_load
    gpx_module.load = patched_load
    gpx_module._gpstitch_gpx_encoding_patched = True
    logger.info("Patched gopro_overlay.gpx.load for locale-independent GPX decoding")
