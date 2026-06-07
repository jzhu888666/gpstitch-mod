"""Patch gopro_overlay layout datetime formatting."""

from __future__ import annotations

import datetime
import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable

from gopro_overlay.entry import Entry

logger = logging.getLogger(__name__)

_WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]


def patch_layout_datetime_formatting() -> None:
    """Keep datetime widgets on the source timeline unless a timezone is requested."""
    import gopro_overlay.layout_xml as layout_xml_module
    from gopro_overlay.layout_xml_attribute import allow_attributes

    if getattr(layout_xml_module, "_gpstitch_layout_datetime_patched", False):
        logger.debug("gopro_overlay.layout_xml datetime formatting already patched")
        return

    original_date_formatter_from_element = layout_xml_module.date_formatter_from_element
    original_create_datetime = layout_xml_module.Widgets.create_datetime

    def patched_date_formatter_from_element(element: ET.Element, entry: Callable[[], Entry]):
        format_string = layout_xml_module.attrib(element, "format")
        truncate = layout_xml_module.iattrib(element, "truncate", d=0)
        timezone_mode = layout_xml_module.attrib(element, "timezone", d="source")
        return _date_formatter(entry, format_string, truncate, timezone_mode)

    @allow_attributes(
        {"x", "y", "size", "format", "truncate", "align", "cache", "rgb", "outline", "outline_width", "timezone"}
    )
    def patched_create_datetime(self, element, entry, **kwargs):
        return layout_xml_module.text(
            at=layout_xml_module.at(element),
            value=patched_date_formatter_from_element(element, entry),
            font=self._font(element, "size", d=16),
            align=layout_xml_module.attrib(element, "align", d="left"),
            cache=layout_xml_module.battrib(element, "cache", d=True),
            fill=layout_xml_module.rgbattr(element, "rgb", d=(255, 255, 255)),
            stroke=layout_xml_module.rgbattr(element, "outline", d=(0, 0, 0)),
            stroke_width=layout_xml_module.iattrib(element, "outline_width", d=2),
        )

    layout_xml_module._gpstitch_original_date_formatter_from_element = original_date_formatter_from_element
    layout_xml_module._gpstitch_original_create_datetime = original_create_datetime
    layout_xml_module.date_formatter_from_element = patched_date_formatter_from_element
    layout_xml_module.Widgets.create_datetime = patched_create_datetime
    layout_xml_module._gpstitch_layout_datetime_patched = True
    logger.info("Patched gopro_overlay.layout_xml datetime formatting")


def _date_formatter(
    entry: Callable[[], Entry],
    format_string: str,
    truncate: int = 0,
    timezone_mode: str = "source",
) -> Callable[[], str]:
    def formatter() -> str:
        dt = _datetime_for_timezone(entry().dt, timezone_mode)
        text = dt.strftime(format_string)
        text = text.replace("{weekday_zh}", f"星期{_WEEKDAY_ZH[dt.weekday()]}")
        if truncate > 0:
            return text[:-truncate]
        return text

    return formatter


def _datetime_for_timezone(dt: datetime.datetime, timezone_mode: str) -> datetime.datetime:
    normalized = timezone_mode.strip().lower()
    if normalized in {"source", "raw", "none"}:
        return dt
    if normalized in {"utc", "z"}:
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(datetime.UTC)
    return dt.astimezone()
