"""Tests for GPStitch-owned default OSD layout generation."""

import xml.etree.ElementTree as ET
from pathlib import Path

from gpstitch.services.renderer import _FONTS_TO_TRY, _localized_default_layout_path, _resolve_layout_path


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
    assert 'timezone="local"' in xml
    assert "GPS 信息" in xml
    assert "公里/小时" in xml
    assert "海拔变化" in xml


def test_default_4k_osd_layout_scales_text_and_local_spacing(temp_dir, monkeypatch):
    monkeypatch.setattr("gpstitch.services.renderer.settings.layout_cache_dir", temp_dir / "layouts")

    path = _localized_default_layout_path("default-3840x2160", "en")
    root = ET.parse(path).getroot()

    speed_metric = root.find(".//component[@type='metric'][@metric='speed']")
    speed_group = root.find("./composite[@name='big_mph']")
    altitude_group = root.find("./composite[@name='altitude']")
    gradient_group = root.find("./composite[@name='gradient']")
    gradient_chart = root.find("./component[@name='gradient_chart']")
    moving_map = root.find("./component[@name='moving_map']")
    journey_map = root.find("./component[@name='journey_map']")
    gps_lock = root.find("./composite[@name='gps_info']/frame[@name='gps-lock']")
    chart_label = root.find("./component[@name='gradient_chart_label']")
    datetime_components = root.findall("./composite[@name='date_and_time']/component[@type='datetime']")

    assert root.attrib["gpstitch_osd_scale"] == "v9:2"
    assert len(datetime_components) == 3
    assert datetime_components[0].attrib["format"] == "%Y/%m/%d"
    assert datetime_components[0].attrib["timezone"] == "local"
    assert datetime_components[0].attrib["size"] == "64"
    assert datetime_components[0].attrib["y"] == "0"
    assert datetime_components[1].attrib["format"] == "{weekday_zh}"
    assert datetime_components[1].attrib["timezone"] == "local"
    assert datetime_components[1].attrib["size"] == "64"
    assert datetime_components[1].attrib["y"] == "80"
    assert datetime_components[2].attrib["format"] == "%H:%M:%S"
    assert datetime_components[2].attrib["timezone"] == "local"
    assert datetime_components[2].attrib["size"] == "64"
    assert datetime_components[2].attrib["y"] == "160"
    assert speed_metric.attrib["size"] == "320"
    assert speed_metric.attrib["x"] == "0"
    assert speed_metric.attrib["y"] == "0"
    assert speed_group.attrib["y"] == "1600"
    assert altitude_group.attrib["y"] == "1960"
    assert gradient_group.attrib["y"] == "1960"
    assert gradient_chart.attrib["y"] == "2008"
    assert chart_label.text == "ALT CHANGE"
    assert chart_label.attrib["x"] == "800"
    assert chart_label.attrib["y"] == "1960"
    assert chart_label.attrib["size"] == "32"
    assert root.find(".//component[@type='metric_unit'][@metric='speed']").attrib["size"] == "32"
    assert root.find(".//component[@type='text']").attrib["size"] == "32"
    assert root.find(".//component[@type='metric'][@metric='lat']").attrib["x"] == "236"
    assert root.find(".//component[@type='metric'][@metric='lat']").attrib["y"] == "48"
    assert root.find(".//component[@type='icon']").attrib["size"] == "128"
    assert moving_map.attrib["x"] == "3288"
    assert moving_map.attrib["y"] == "200"
    assert journey_map.attrib["x"] == "3288"
    assert journey_map.attrib["y"] == "752"
    assert gps_lock.attrib["x"] == "448"
    assert gps_lock.attrib["y"] == "0"


def test_dji_drone_layouts_keep_gps_lock_above_text_rows():
    layouts_dir = Path(__file__).parents[3] / "src" / "gpstitch" / "layouts"

    for path in layouts_dir.glob("dji-drone-*.xml"):
        root = ET.parse(path).getroot()
        gps_info = root.find("./composite[@name='gps_info']")
        gps_lock = root.find("./composite[@name='gps_info']/frame[@name='gps-lock']")
        moving_map = root.find("./component[@name='moving_map']")

        assert gps_info is not None, path.name
        assert gps_lock is not None, path.name
        assert moving_map is not None, path.name
        assert gps_lock.attrib["y"] == "0", path.name
        assert int(gps_lock.attrib["x"]) + int(gps_lock.attrib["width"]) <= int(moving_map.attrib["size"])


def test_custom_layout_path_is_not_rewritten(temp_dir):
    custom = temp_dir / "custom.xml"
    custom.write_text('<layout><composite name="temperature" /></layout>', encoding="utf-8")

    resolved = _resolve_layout_path(str(custom), language="zh-CN")

    assert resolved == custom
    assert 'name="temperature"' in custom.read_text(encoding="utf-8")


def test_default_osd_font_candidates_prioritize_chinese_fonts():
    assert _FONTS_TO_TRY.index("C:/Windows/Fonts/msyh.ttc") < _FONTS_TO_TRY.index("Roboto-Medium.ttf")
