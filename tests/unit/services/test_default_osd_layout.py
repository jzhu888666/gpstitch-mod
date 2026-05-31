"""Tests for GPStitch-owned default OSD layout generation."""

import xml.etree.ElementTree as ET

from gpstitch.services.renderer import _localized_default_layout_path, _resolve_layout_path


def test_default_osd_layout_removes_bottom_right_widgets(temp_dir, monkeypatch):
    monkeypatch.setattr("gpstitch.services.renderer.settings.layout_cache_dir", temp_dir / "layouts")

    path = _localized_default_layout_path("default-1920x1080", "zh-CN")
    xml = path.read_text(encoding="utf-8")

    assert "name=\"temperature\"" not in xml
    assert "name=\"cadence\"" not in xml
    assert "name=\"heartbeat\"" not in xml
    assert 'format="%Y/%m/%d"' in xml
    assert 'format="{weekday_zh}"' in xml
    assert 'format="%H:%M:%S"' in xml
    assert 'format="%Y/%m/%d {weekday_zh}"' not in xml
    assert 'timezone="source"' in xml
    assert "GPS 信息" in xml


def test_default_4k_osd_layout_scales_text_and_local_spacing(temp_dir, monkeypatch):
    monkeypatch.setattr("gpstitch.services.renderer.settings.layout_cache_dir", temp_dir / "layouts")

    path = _localized_default_layout_path("default-3840x2160", "en")
    root = ET.parse(path).getroot()

    speed_metric = root.find(".//component[@type='metric'][@metric='speed']")
    speed_group = root.find("./composite[@name='big_mph']")
    altitude_group = root.find("./composite[@name='altitude']")
    gradient_group = root.find("./composite[@name='gradient']")
    moving_map = root.find("./component[@name='moving_map']")
    journey_map = root.find("./component[@name='journey_map']")
    datetime_components = root.findall("./composite[@name='date_and_time']/component[@type='datetime']")

    assert root.attrib["gpstitch_osd_scale"] == "v5:2"
    assert len(datetime_components) == 3
    assert datetime_components[0].attrib["format"] == "%Y/%m/%d"
    assert datetime_components[0].attrib["timezone"] == "source"
    assert datetime_components[0].attrib["size"] == "64"
    assert datetime_components[0].attrib["y"] == "0"
    assert datetime_components[1].attrib["format"] == "{weekday_zh}"
    assert datetime_components[1].attrib["timezone"] == "source"
    assert datetime_components[1].attrib["size"] == "64"
    assert datetime_components[1].attrib["y"] == "80"
    assert datetime_components[2].attrib["format"] == "%H:%M:%S"
    assert datetime_components[2].attrib["timezone"] == "source"
    assert datetime_components[2].attrib["size"] == "64"
    assert datetime_components[2].attrib["y"] == "160"
    assert speed_metric.attrib["size"] == "320"
    assert speed_metric.attrib["x"] == "0"
    assert speed_metric.attrib["y"] == "0"
    assert speed_group.attrib["y"] == "1600"
    assert altitude_group.attrib["y"] == "1960"
    assert gradient_group.attrib["y"] == "1960"
    assert root.find(".//component[@type='metric_unit'][@metric='speed']").attrib["size"] == "32"
    assert root.find(".//component[@type='text']").attrib["size"] == "32"
    assert root.find(".//component[@type='metric'][@metric='lat']").attrib["x"] == "236"
    assert root.find(".//component[@type='metric'][@metric='lat']").attrib["y"] == "48"
    assert root.find(".//component[@type='icon']").attrib["size"] == "128"
    assert moving_map.attrib["x"] == "3288"
    assert moving_map.attrib["y"] == "200"
    assert journey_map.attrib["x"] == "3288"
    assert journey_map.attrib["y"] == "752"


def test_custom_layout_path_is_not_rewritten(temp_dir):
    custom = temp_dir / "custom.xml"
    custom.write_text('<layout><composite name="temperature" /></layout>', encoding="utf-8")

    resolved = _resolve_layout_path(str(custom), language="zh-CN")

    assert resolved == custom
    assert 'name="temperature"' in custom.read_text(encoding="utf-8")
