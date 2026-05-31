"""Patch gopro_overlay layout XML loading to avoid locale-dependent decoding."""

from __future__ import annotations

import logging
from importlib.resources import as_file, files
from pathlib import Path

from gpstitch.patches.xml_encoding import decode_xml_bytes

logger = logging.getLogger(__name__)


def patch_layout_xml_encoding() -> None:
    """Patch gopro_overlay.layout_xml.load_xml_layout to read XML as UTF-8.

    Upstream reads layout XML with ``open()`` and no encoding. Localized GPStitch
    default layouts are cached as UTF-8 XML, so Chinese Windows can fail with
    GBK decode errors during preview rendering.
    """
    import gopro_overlay.layout_xml as layout_xml_module
    from gopro_overlay import layouts

    if getattr(layout_xml_module, "_gpstitch_layout_encoding_patched", False):
        logger.debug("gopro_overlay.layout_xml.load_xml_layout already patched for XML encoding")
        return

    original_load_xml_layout = layout_xml_module.load_xml_layout

    def patched_load_xml_layout(filepath: Path):
        path = Path(filepath)
        if path.exists():
            return decode_xml_bytes(path.read_bytes())

        with as_file(files(layouts) / f"{path.name}.xml") as fn:
            return decode_xml_bytes(Path(fn).read_bytes())

    layout_xml_module._gpstitch_original_load_xml_layout = original_load_xml_layout
    layout_xml_module.load_xml_layout = patched_load_xml_layout
    layout_xml_module._gpstitch_layout_encoding_patched = True
    logger.info("Patched gopro_overlay.layout_xml.load_xml_layout for UTF-8 XML decoding")
