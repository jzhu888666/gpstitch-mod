"""Tests for locale-independent GPX decoding patches."""

from pathlib import Path

NON_ASCII_TRACK_NAME = "\u9a91\u884c\u8f68\u8ff9"

GPX_WITH_NON_ASCII = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="\u6d4b\u8bd5\u8bbe\u5907" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>{NON_ASCII_TRACK_NAME}</name>
    <trkseg>
      <trkpt lat="30.000000" lon="104.000000">
        <ele>500.0</ele>
        <time>2026-05-10T00:00:00Z</time>
      </trkpt>
      <trkpt lat="30.000100" lon="104.000100">
        <ele>501.0</ele>
        <time>2026-05-10T00:00:01Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def test_decode_prefers_utf8_before_system_encoding(monkeypatch):
    """UTF-8 GPX bytes should decode even when the Windows locale is GBK."""
    from gpstitch.patches import gpx_encoding_patches

    monkeypatch.setattr(gpx_encoding_patches.locale, "getpreferredencoding", lambda _do_setlocale=False: "gbk")

    decoded = gpx_encoding_patches._decode_gpx_bytes(GPX_WITH_NON_ASCII.encode("utf-8"))

    assert NON_ASCII_TRACK_NAME in decoded


def test_patched_load_external_reads_utf8_gpx_with_non_ascii(tmp_path):
    """gopro_overlay.load_external should parse UTF-8 GPX independent of locale."""
    from gopro_overlay.loading import load_external
    from gopro_overlay.units import units
    from gpstitch.patches.gpx_encoding_patches import patch_gpx_file_encoding

    patch_gpx_file_encoding()
    gpx_path = Path(tmp_path) / "track.gpx"
    gpx_path.write_bytes(GPX_WITH_NON_ASCII.encode("utf-8"))

    timeseries = load_external(gpx_path, units)

    assert len(timeseries.items()) == 2
