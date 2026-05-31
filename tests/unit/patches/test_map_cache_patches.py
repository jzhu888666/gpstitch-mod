"""Tests for map cache runtime patches."""


def test_map_styler_uses_https_for_osm_tiles():
    from gpstitch.patches.map_cache_patches import patch_map_renderer_cache_dir
    from gopro_overlay.geo import MapStyler

    patch_map_renderer_cache_dir()

    attrs, _ = MapStyler().provide("osm")
    assert attrs["url"].startswith("https://")
    assert "tile.openstreetmap.org" in attrs["url"]
