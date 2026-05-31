import xml.etree.ElementTree as ET

from gpstitch.services.renderer import (
    _layout_without_map_components_path,
    _resolve_layout_path,
    _xml_without_map_components,
)


def test_layout_without_map_components_removes_quick_preview_maps():
    original = _resolve_layout_path("dji-drone-1920x1080", language="zh-CN")
    stripped = _layout_without_map_components_path("dji-drone-1920x1080", language="zh-CN")

    assert stripped != original

    root = ET.parse(stripped).getroot()
    component_types = {elem.attrib.get("type") for elem in root.iter("component")}
    element_names = {elem.attrib.get("name") for elem in root.iter()}

    assert "moving_map" not in component_types
    assert "journey_map" not in component_types
    assert "moving_map" not in element_names
    assert "journey_map" not in element_names
    assert "date_time" in element_names
    assert "gps_info" in element_names


def test_xml_without_map_components_prunes_empty_wrappers():
    xml_content = (
        '<layout><translate x="10" y="20"><component type="moving_journey_map" name="route"/></translate>'
        '<component type="metric" name="speed"/></layout>'
    )

    root = ET.fromstring(_xml_without_map_components(xml_content))

    assert root.find(".//component[@type='moving_journey_map']") is None
    assert root.find("./translate") is None
    assert root.find("./component[@name='speed']") is not None
