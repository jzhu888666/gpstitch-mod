"""Patch gopro_overlay map widgets to render through AMap JSAPI snapshots."""

from __future__ import annotations

import logging

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def patch_amap_jsapi_rendering() -> None:
    """Replace gopro_overlay XML map widget factories with AMap-backed widgets."""
    import gopro_overlay.layout_xml as layout_xml_module

    if getattr(layout_xml_module, "_gpstitch_amap_render_patched", False):
        logger.debug("gopro_overlay AMap JSAPI render patch already applied")
        return

    from gopro_overlay.point import Coordinate
    from gopro_overlay.widgets.map import Journey, MaybeRoundedBorder
    from gopro_overlay.widgets.widgets import Widget

    from gpstitch.services.amap_jsapi_renderer import AMapJSAPISnapshotRenderer
    from gpstitch.services.amap_settings import amap_settings_service

    runtime_config = amap_settings_service.get_runtime_config()
    renderer = AMapJSAPISnapshotRenderer(runtime_config)

    class AMapMovingMapWidget(Widget):
        def __init__(
            self,
            *,
            at,
            location,
            size: int,
            zoom: int,
            corner_radius: int,
            opacity: float,
        ) -> None:
            self.at = at
            self.location = location
            self.size = size
            self.zoom = zoom
            self.border = MaybeRoundedBorder(size=size, corner_radius=corner_radius, opacity=opacity)

        def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
            location = self.location()
            if not _valid_location(location):
                return
            frame = renderer.render_moving(
                lat=location.lat,
                lon=location.lon,
                size=self.size,
                zoom=self.zoom,
            )
            image.alpha_composite(self.border.rounded(frame), self.at.tuple())

    class AMapJourneyMapWidget(Widget):
        def __init__(
            self,
            *,
            at,
            location,
            timeseries,
            privacy_zone,
            size: int,
            corner_radius: int,
            opacity: float,
            line_fill: tuple[int, int, int],
            line_width: int,
            marker_fill: tuple[int, int, int],
            marker_outline: tuple[int, int, int],
        ) -> None:
            self.at = at
            self.location = location
            self.timeseries = timeseries
            self.privacy_zone = privacy_zone
            self.size = size
            self.line_fill = line_fill
            self.line_width = line_width
            self.marker_fill = marker_fill
            self.marker_outline = marker_outline
            self.border = MaybeRoundedBorder(size=size, corner_radius=corner_radius, opacity=opacity)
            self._route: list[tuple[float, float]] | None = None

        def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw) -> None:
            location = self.location()
            if not _valid_location(location):
                return
            route = self._route_points()
            if not route:
                route = [(location.lat, location.lon)]
            frame = renderer.render_journey(
                route=route,
                current=(location.lat, location.lon),
                size=self.size,
                line_fill=self.line_fill,
                line_width=self.line_width,
                marker_fill=self.marker_fill,
                marker_outline=self.marker_outline,
            )
            image.alpha_composite(self.border.rounded(frame), self.at.tuple())

        def _route_points(self) -> list[tuple[float, float]]:
            if self._route is not None:
                return self._route

            journey = Journey()
            self.timeseries.process(journey.accept)
            self._route = [
                (location.lat, location.lon)
                for location in journey.locations
                if _valid_location(location) and not self.privacy_zone.encloses(location)
            ]
            return self._route

    original_create_moving_map = layout_xml_module.Widgets.create_moving_map
    original_create_journey_map = layout_xml_module.Widgets.create_journey_map
    original_create_moving_journey_map = layout_xml_module.Widgets.create_moving_journey_map

    def create_moving_map(self, element, entry, **kwargs):
        return AMapMovingMapWidget(
            at=layout_xml_module.at(element),
            location=lambda: entry().point,
            size=layout_xml_module.iattrib(element, "size", d=256),
            zoom=layout_xml_module.iattrib(element, "zoom", d=16, r=range(1, 20)),
            corner_radius=layout_xml_module.iattrib(element, "corner_radius", 0),
            opacity=layout_xml_module.fattrib(element, "opacity", 0.7, r=layout_xml_module.FloatRange(0.0, 1.0)),
        )

    def create_journey_map(self, element, entry, **kwargs):
        return AMapJourneyMapWidget(
            at=layout_xml_module.at(element),
            location=lambda: entry().point,
            timeseries=self.framemeta,
            privacy_zone=self.privacy,
            size=layout_xml_module.iattrib(element, "size", d=256),
            corner_radius=layout_xml_module.iattrib(element, "corner_radius", 0),
            opacity=layout_xml_module.fattrib(element, "opacity", 0.7, r=layout_xml_module.FloatRange(0.0, 1.0)),
            line_fill=layout_xml_module.rgbattr(element, "fill", d=(31, 143, 255)),
            line_width=layout_xml_module.iattrib(element, "line-width", d=5),
            marker_fill=layout_xml_module.rgbattr(element, "loc-fill", d=(0, 0, 255)),
            marker_outline=layout_xml_module.rgbattr(element, "loc-outline", d=(0, 0, 0)),
        )

    def create_moving_journey_map(self, element, entry, **kwargs):
        return AMapJourneyMapWidget(
            at=Coordinate(0, 0),
            location=lambda: entry().point,
            timeseries=self.framemeta,
            privacy_zone=self.privacy,
            size=layout_xml_module.iattrib(element, "size", d=256),
            corner_radius=0,
            opacity=1.0,
            line_fill=layout_xml_module.rgbattr(element, "fill", d=(31, 143, 255)),
            line_width=layout_xml_module.iattrib(element, "line-width", d=5),
            marker_fill=layout_xml_module.rgbattr(element, "loc-fill", d=(0, 0, 255)),
            marker_outline=layout_xml_module.rgbattr(element, "loc-outline", d=(0, 0, 0)),
        )

    layout_xml_module.Widgets._gpstitch_original_create_moving_map = original_create_moving_map
    layout_xml_module.Widgets._gpstitch_original_create_journey_map = original_create_journey_map
    layout_xml_module.Widgets._gpstitch_original_create_moving_journey_map = original_create_moving_journey_map
    layout_xml_module.Widgets.create_moving_map = create_moving_map
    layout_xml_module.Widgets.create_journey_map = create_journey_map
    layout_xml_module.Widgets.create_moving_journey_map = create_moving_journey_map
    layout_xml_module._gpstitch_amap_render_patched = True
    logger.info("Patched gopro_overlay map widgets for AMap JSAPI video rendering")


def _valid_location(location) -> bool:
    return (
        location is not None
        and getattr(location, "lat", None) is not None
        and getattr(location, "lon", None) is not None
    )
