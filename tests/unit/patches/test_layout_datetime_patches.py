"""Tests for GPStitch datetime layout patches."""

import datetime
import xml.etree.ElementTree as ET

from gopro_overlay.entry import Entry


def test_datetime_formatter_keeps_source_timezone_and_formats_chinese_weekday():
    import gopro_overlay.layout_xml as layout_xml_module
    from gpstitch.patches.layout_datetime_patches import patch_layout_datetime_formatting

    patch_layout_datetime_formatting()
    element = ET.fromstring(
        '<component type="datetime" format="%Y/%m/%d {weekday_zh}" timezone="source" />'
    )
    entry = Entry(datetime.datetime(2026, 5, 10, 10, 56, 45, tzinfo=datetime.UTC))

    formatter = layout_xml_module.date_formatter_from_element(element, lambda: entry)

    assert formatter() == "2026/05/10 星期日"


def test_datetime_formatter_supports_weekday_only_format():
    import gopro_overlay.layout_xml as layout_xml_module
    from gpstitch.patches.layout_datetime_patches import patch_layout_datetime_formatting

    patch_layout_datetime_formatting()
    element = ET.fromstring('<component type="datetime" format="{weekday_zh}" timezone="source" />')
    entry = Entry(datetime.datetime(2026, 5, 10, 10, 56, 45, tzinfo=datetime.UTC))

    formatter = layout_xml_module.date_formatter_from_element(element, lambda: entry)

    assert formatter() == "星期日"


def test_datetime_widget_accepts_timezone_attribute():
    import gopro_overlay.layout_xml as layout_xml_module
    from gpstitch.patches.layout_datetime_patches import patch_layout_datetime_formatting

    patch_layout_datetime_formatting()
    element = ET.fromstring(
        '<component type="datetime" x="0" y="0" format="%H:%M:%S" timezone="source" />'
    )
    entry = Entry(datetime.datetime(2026, 5, 10, 10, 56, 45, tzinfo=datetime.UTC))

    class FakeWidgets:
        def _font(self, _element, _name, d):
            return f"font-{d}"

    widget = layout_xml_module.Widgets.create_datetime(FakeWidgets(), element, lambda: entry)

    assert widget.value() == "10:56:45"
