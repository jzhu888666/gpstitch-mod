"""Tests for locale-independent layout XML decoding patches."""

from pathlib import Path

LOCALIZED_LAYOUT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<layout>
  <component type="text" name="gps-label">\u7eac\u5ea6</component>
</layout>
"""


def test_patched_load_xml_layout_reads_utf8_layout_when_locale_is_gbk(monkeypatch, tmp_path):
    """Localized UTF-8 layouts should load on Chinese Windows."""
    import gopro_overlay.layout_xml as layout_xml_module
    from gpstitch.patches import xml_encoding
    from gpstitch.patches.layout_encoding_patches import patch_layout_xml_encoding

    monkeypatch.setattr(xml_encoding.locale, "getpreferredencoding", lambda _do_setlocale=False: "gbk")

    patch_layout_xml_encoding()
    layout_path = Path(tmp_path) / "localized.xml"
    layout_path.write_bytes(LOCALIZED_LAYOUT_XML.encode("utf-8"))

    loaded = layout_xml_module.load_xml_layout(layout_path)

    assert "\u7eac\u5ea6" in loaded
