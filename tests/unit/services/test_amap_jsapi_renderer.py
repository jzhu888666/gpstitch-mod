"""Tests for backend AMap JSAPI snapshot rendering helpers."""

import math
from types import SimpleNamespace

import pytest
from PIL import Image


def test_wgs84_points_are_converted_to_amap_gcj02():
    from gpstitch.services.amap_jsapi_renderer import _to_amap_point

    point = _to_amap_point(29.698164997988393, 92.22652316093446)

    assert point["lat"] == pytest.approx(29.695315106096245)
    assert point["lng"] == pytest.approx(92.22754311668311)


def test_outside_china_points_are_not_shifted():
    from gpstitch.services.amap_jsapi_renderer import _to_amap_point

    point = _to_amap_point(37.7749, -122.4194)

    assert point == {"lat": 37.7749, "lng": -122.4194}


def test_render_journey_uses_preconverted_amap_points(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
    )
    captured = {}

    def fake_render(options):
        captured.setdefault("options", options)
        return AMapSnapshot(Image.new("RGBA", (256, 256), (255, 255, 255, 255)), {
            "center": {"lat": 29.695315106096245, "lng": 92.22754311668311},
            "zoom": 16,
        })

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)

    image = renderer.render_journey(
        route=[(29.698164997988393, 92.22652316093446)],
        current=(29.698164997988393, 92.22652316093446),
        size=256,
    )

    assert captured["options"]["kind"] == "journey-base"
    assert "current" not in captured["options"]
    assert captured["options"]["drawRoute"] is False
    assert captured["options"]["drawMarker"] is False
    assert captured["options"]["fitPadding"] == [0, 0, 0, 0]
    assert captured["options"]["route"][0] == pytest.approx(
        {"lat": 29.695315106096245, "lng": 92.22754311668311}
    )
    assert image.getpixel((128, 128))[:3] == (0, 0, 255)


def test_render_moving_uses_quantized_base_without_browser_marker(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
    )
    captured = []

    def fake_render(options):
        captured.append(options)
        return AMapSnapshot(Image.new("RGBA", (options["size"], options["size"]), (255, 255, 255, 255)), {})

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)

    image = renderer.render_moving(lat=29.698164997988393, lon=92.22652316093446, size=256, zoom=17)

    assert captured[0]["kind"] == "moving-base"
    assert captured[0]["size"] == int(math.sqrt((256**2) * 2))
    assert captured[0]["layerType"] == "standard"
    assert captured[0]["drawMarker"] is False
    assert "current" not in captured[0]
    assert image.size == (256, 256)
    assert _has_blue_marker_near_center(image)


def test_render_moving_does_not_draw_route_on_cached_base(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
    )
    captured = []

    def fake_render(options):
        captured.append(options)
        return AMapSnapshot(Image.new("RGBA", (options["size"], options["size"]), (255, 255, 255, 255)), {})

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)

    image = renderer.render_moving(
        lat=29.698164997988393,
        lon=92.22652316093446,
        route=[
            (29.698164997988393, 92.22652316093446),
            (29.698164997988393, 92.22752316093446),
        ],
        size=256,
        zoom=17,
    )

    assert captured[0]["route"] == []
    assert not _has_green_route_pixel(image)


def test_render_moving_rotation_is_passed_to_amap(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
    )
    captured = []

    def fake_render(options):
        captured.append(options)
        return AMapSnapshot(Image.new("RGBA", (options["size"], options["size"]), (255, 255, 255, 255)), {})

    def fail_rotate(*_args, **_kwargs):
        raise AssertionError("AMap snapshots should not be rotated with PIL")

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)
    monkeypatch.setattr(Image.Image, "rotate", fail_rotate)

    image = renderer.render_moving(
        lat=29.698164997988393,
        lon=92.22652316093446,
        size=256,
        zoom=17,
        rotation_degrees=90,
    )

    assert captured[0]["rotation"] == 270
    assert image.size == (256, 256)
    assert _has_blue_marker_near_center(image)


def test_render_moving_satellite_style_uses_satellite_roadnet_layer(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
        map_style="amap-jsapi-satellite",
    )
    captured = []

    def fake_render(options):
        captured.append(options)
        return AMapSnapshot(Image.new("RGBA", (options["size"], options["size"]), (255, 255, 255, 255)), {})

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)

    renderer.render_moving(lat=29.698164997988393, lon=92.22652316093446, size=256, zoom=17)

    assert captured[0]["layerType"] == "satellite-roadnet"


def test_render_mixed_style_uses_standard_moving_and_satellite_journey(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
        map_style="amap-jsapi-mixed",
    )
    captured = []

    def fake_render(options):
        captured.append(options)
        return AMapSnapshot(Image.new("RGBA", (options["size"], options["size"]), (255, 255, 255, 255)), {})

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)

    renderer.render_moving(lat=29.698164997988393, lon=92.22652316093446, size=256, zoom=17)
    renderer.render_journey(
        route=[(29.698164997988393, 92.22652316093446), (29.698264997988394, 92.22662316093445)],
        current=(29.698164997988393, 92.22652316093446),
        size=256,
    )

    assert [options["layerType"] for options in captured] == ["standard", "satellite-roadnet"]


def test_render_journey_rotation_uses_amap_rotation_and_centers_marker(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import (
        AMapJSAPISnapshotRenderer,
        AMapSnapshot,
        _journey_rotation_backing_size,
        _rotation_safe_padding,
    )

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
    )
    captured = {}

    def fake_render(options):
        captured.setdefault("options", options)
        return AMapSnapshot(Image.new("RGBA", (options["size"], options["size"]), (255, 255, 255, 255)), {
            "center": {"lat": 29.695315106096245, "lng": 92.22754311668311},
            "zoom": 16,
        })

    def fail_rotate(*_args, **_kwargs):
        raise AssertionError("AMap snapshots should not be rotated with PIL")

    monkeypatch.setattr(renderer, "_render_cached_snapshot", fake_render)
    monkeypatch.setattr(Image.Image, "rotate", fail_rotate)

    image = renderer.render_journey(
        route=[
            (29.698164997988393, 92.22652316093446),
            (29.698164997988393, 92.22752316093446),
        ],
        current=(29.698164997988393, 92.22652316093446),
        size=256,
        rotation_degrees=90,
    )

    assert captured["options"]["size"] == _journey_rotation_backing_size(256)
    assert captured["options"]["rotation"] == 270
    assert captured["options"]["fitPadding"] == [_rotation_safe_padding(256)] * 4
    assert captured["options"]["drawRoute"] is False
    assert image.size == (256, 256)
    assert image.getpixel((128, 128))[:3] == (0, 0, 255)


def test_renderer_html_hides_amap_attribution():
    from gpstitch.services.amap_jsapi_renderer import _renderer_html

    html = _renderer_html(SimpleNamespace(key="test-key", security_js_code="test-security"))

    assert ".amap-logo" in html
    assert ".amap-copyright" in html
    assert "display: none !important" in html
    assert "map.setFitView(overlays, false, fitPadding)" in html
    assert "viewMode: '3D'" in html
    assert "pitch: 0" in html
    assert "pitchEnable: false" in html
    assert "new AMap.TileLayer.Satellite" in html
    assert "new AMap.TileLayer.RoadNet" in html
    assert "rotation: mapRotation === null ? 0 : mapRotation" in html
    assert "map.setRotation(rotation)" in html


def test_close_moving_points_share_quantized_center():
    from gpstitch.services.amap_jsapi_renderer import _quantize_point, _to_amap_point

    first = _to_amap_point(29.698164997988393, 92.22652316093446)
    second = _to_amap_point(29.6981655, 92.2265237)

    assert _quantize_point(first, 17, 16) == _quantize_point(second, 17, 16)


def test_cached_snapshots_are_reused_from_memory(monkeypatch, tmp_path):
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer, AMapSnapshot

    renderer = AMapJSAPISnapshotRenderer(
        SimpleNamespace(
            configured=True,
            validated=True,
            key="test-key",
            security_js_code="test-security",
            key_fingerprint="test-fp",
        ),
        cache_dir=tmp_path,
    )
    calls = 0

    def fake_render(_options):
        nonlocal calls
        calls += 1
        return AMapSnapshot(Image.new("RGBA", (128, 128), (255, 255, 255, 255)), {"zoom": 16})

    monkeypatch.setattr(renderer, "_render_snapshot", fake_render)
    options = {
        "kind": "moving-base",
        "size": 128,
        "zoom": 16,
        "center": {"lat": 30.0, "lng": 120.0},
        "route": [],
        "drawMarker": False,
    }

    first = renderer._render_cached_snapshot(options)
    second = renderer._render_cached_snapshot(options)

    assert first is second
    assert calls == 1


def _has_blue_marker_near_center(image: Image.Image) -> bool:
    for x in range(112, 145):
        for y in range(112, 145):
            if image.getpixel((x, y))[:3] == (0, 0, 255):
                return True
    return False


def _has_green_route_pixel(image: Image.Image) -> bool:
    for x in range(140, 220):
        for y in range(120, 137):
            if image.getpixel((x, y))[:3] == (0, 255, 0):
                return True
    return False
