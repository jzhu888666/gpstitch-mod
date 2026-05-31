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
    from gopro_overlay.widgets.map import MaybeRoundedBorder
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
            azimuth,
            timeseries,
            privacy_zone,
            size: int,
            zoom: int,
            corner_radius: int,
            opacity: float,
            rotate: bool,
            line_fill: tuple[int, int, int],
            line_width: int,
            marker_fill: tuple[int, int, int],
            marker_outline: tuple[int, int, int],
        ) -> None:
            self.at = at
            self.location = location
            self.azimuth = azimuth
            self.timeseries = timeseries
            self.privacy_zone = privacy_zone
            self.size = size
            self.zoom = zoom
            self.rotate = rotate
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
            rotation_degrees = _rotation_degrees(self.azimuth(), self.rotate, route, location)
            frame = renderer.render_moving(
                lat=location.lat,
                lon=location.lon,
                route=route,
                size=self.size,
                zoom=self.zoom,
                rotation_degrees=rotation_degrees,
                line_fill=self.line_fill,
                line_width=self.line_width,
                marker_fill=self.marker_fill,
                marker_outline=self.marker_outline,
            )
            image.alpha_composite(self.border.rounded(frame), self.at.tuple())

        def _route_points(self) -> list[tuple[float, float]]:
            if self._route is not None:
                return self._route
            self._route = _route_points(self.timeseries, self.privacy_zone)
            return self._route

    class AMapJourneyMapWidget(Widget):
        def __init__(
            self,
            *,
            at,
            location,
            azimuth,
            timeseries,
            privacy_zone,
            size: int,
            corner_radius: int,
            opacity: float,
            rotate: bool,
            line_fill: tuple[int, int, int],
            line_width: int,
            marker_fill: tuple[int, int, int],
            marker_outline: tuple[int, int, int],
        ) -> None:
            self.at = at
            self.location = location
            self.azimuth = azimuth
            self.timeseries = timeseries
            self.privacy_zone = privacy_zone
            self.size = size
            self.rotate = rotate
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
            rotation_degrees = _rotation_degrees(self.azimuth(), self.rotate, route, location)
            frame = renderer.render_journey(
                route=route,
                current=(location.lat, location.lon),
                size=self.size,
                rotation_degrees=rotation_degrees,
                line_fill=self.line_fill,
                line_width=self.line_width,
                marker_fill=self.marker_fill,
                marker_outline=self.marker_outline,
            )
            image.alpha_composite(self.border.rounded(frame), self.at.tuple())

        def _route_points(self) -> list[tuple[float, float]]:
            if self._route is not None:
                return self._route
            self._route = _route_points(self.timeseries, self.privacy_zone)
            return self._route

    original_create_moving_map = layout_xml_module.Widgets.create_moving_map
    original_create_journey_map = layout_xml_module.Widgets.create_journey_map
    original_create_moving_journey_map = layout_xml_module.Widgets.create_moving_journey_map

    def create_moving_map(self, element, entry, **kwargs):
        return AMapMovingMapWidget(
            at=layout_xml_module.at(element),
            location=lambda: entry().point,
            azimuth=lambda: entry().azi,
            timeseries=self.framemeta,
            privacy_zone=self.privacy,
            size=layout_xml_module.iattrib(element, "size", d=256),
            zoom=layout_xml_module.iattrib(element, "zoom", d=16, r=range(1, 20)),
            corner_radius=layout_xml_module.iattrib(element, "corner_radius", 0),
            opacity=layout_xml_module.fattrib(element, "opacity", 0.7, r=layout_xml_module.FloatRange(0.0, 1.0)),
            rotate=layout_xml_module.battrib(element, "rotate", d=True),
            line_fill=layout_xml_module.rgbattr(element, "fill", d=(31, 143, 255)),
            line_width=layout_xml_module.iattrib(element, "line-width", d=5),
            marker_fill=layout_xml_module.rgbattr(element, "loc-fill", d=(0, 0, 255)),
            marker_outline=layout_xml_module.rgbattr(element, "loc-outline", d=(0, 0, 0)),
        )

    def create_journey_map(self, element, entry, **kwargs):
        return AMapJourneyMapWidget(
            at=layout_xml_module.at(element),
            location=lambda: entry().point,
            azimuth=lambda: entry().azi,
            timeseries=self.framemeta,
            privacy_zone=self.privacy,
            size=layout_xml_module.iattrib(element, "size", d=256),
            corner_radius=layout_xml_module.iattrib(element, "corner_radius", 0),
            opacity=layout_xml_module.fattrib(element, "opacity", 0.7, r=layout_xml_module.FloatRange(0.0, 1.0)),
            rotate=layout_xml_module.battrib(element, "rotate", d=True),
            line_fill=layout_xml_module.rgbattr(element, "fill", d=(31, 143, 255)),
            line_width=layout_xml_module.iattrib(element, "line-width", d=5),
            marker_fill=layout_xml_module.rgbattr(element, "loc-fill", d=(0, 0, 255)),
            marker_outline=layout_xml_module.rgbattr(element, "loc-outline", d=(0, 0, 0)),
        )

    def create_moving_journey_map(self, element, entry, **kwargs):
        return AMapJourneyMapWidget(
            at=Coordinate(0, 0),
            location=lambda: entry().point,
            azimuth=lambda: entry().azi,
            timeseries=self.framemeta,
            privacy_zone=self.privacy,
            size=layout_xml_module.iattrib(element, "size", d=256),
            corner_radius=0,
            opacity=1.0,
            rotate=layout_xml_module.battrib(element, "rotate", d=True),
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


def _route_points(timeseries, privacy_zone) -> list[tuple[float, float]]:
    from gopro_overlay.widgets.map import Journey

    journey = Journey()
    timeseries.process(journey.accept)
    return [
        (location.lat, location.lon)
        for location in journey.locations
        if _valid_location(location) and not privacy_zone.encloses(location)
    ]


def _rotation_degrees(azimuth, rotate: bool, route: list[tuple[float, float]], location) -> float | None:
    if not rotate:
        return None
    if azimuth is not None:
        try:
            azi = float(azimuth.to("degree").magnitude)
            return azi if azi >= 0 else 360 + azi
        except Exception:
            pass
    return _route_heading(route, (location.lat, location.lon))


def _route_heading(route: list[tuple[float, float]], current: tuple[float, float]) -> float | None:
    if len(route) < 2:
        return None
    current_lat, current_lon = current
    nearest_index = min(
        range(len(route)),
        key=lambda index: (route[index][0] - current_lat) ** 2 + (route[index][1] - current_lon) ** 2,
    )
    start_index = max(0, nearest_index - 1)
    end_index = min(len(route) - 1, nearest_index + 1)
    if start_index == end_index:
        return None
    return _bearing_degrees(route[start_index], route[end_index])


def _bearing_degrees(start: tuple[float, float], end: tuple[float, float]) -> float | None:
    import math

    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lon = lon2 - lon1
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    if x == 0 and y == 0:
        return None
    return (math.degrees(math.atan2(y, x)) + 360) % 360
