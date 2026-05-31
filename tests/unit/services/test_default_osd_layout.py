"""Tests for GPStitch-owned default OSD layout generation."""

from gpstitch.services.renderer import _localized_default_layout_path, _resolve_layout_path


def test_default_osd_layout_removes_bottom_right_widgets():
    path = _localized_default_layout_path("default-1920x1080", "zh-CN")
    xml = path.read_text(encoding="utf-8")

    assert "name=\"temperature\"" not in xml
    assert "name=\"cadence\"" not in xml
    assert "name=\"heartbeat\"" not in xml
    assert "GPS 信息" in xml


def test_custom_layout_path_is_not_rewritten(temp_dir):
    custom = temp_dir / "custom.xml"
    custom.write_text('<layout><composite name="temperature" /></layout>', encoding="utf-8")

    resolved = _resolve_layout_path(str(custom), language="zh-CN")

    assert resolved == custom
    assert 'name="temperature"' in custom.read_text(encoding="utf-8")
