"""Tests for backend AMap JSAPI snapshot rendering helpers."""

from types import SimpleNamespace

import pytest


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
    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer

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
    monkeypatch.setattr(renderer, "_render_cached", lambda options: captured.setdefault("options", options))

    renderer.render_journey(
        route=[(29.698164997988393, 92.22652316093446)],
        current=(29.698164997988393, 92.22652316093446),
        size=256,
    )

    assert captured["options"]["current"] == pytest.approx(
        {"lat": 29.695315106096245, "lng": 92.22754311668311}
    )
    assert captured["options"]["route"][0] == pytest.approx(
        {"lat": 29.695315106096245, "lng": 92.22754311668311}
    )
