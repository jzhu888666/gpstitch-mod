"""Project-local map tile cache warmup helpers."""

from __future__ import annotations

import logging
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from gpstitch.config import settings
from gpstitch.models.schemas import MapCacheWarmupResponse
from gpstitch.services.file_manager import file_manager
from gpstitch.services.localization import t

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutePoint:
    lat: float
    lon: float


class MapCacheService:
    """Warm and expose the map cache used by previews and render subprocesses."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or settings.map_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def warm_session_cache(
        self,
        session_id: str,
        map_style: str = "osm",
        language: str | None = None,
    ) -> MapCacheWarmupResponse:
        """Warm map cache tiles for a session route.

        This is intentionally bounded. Preview/render still lazily fetch missing
        tiles, but this prepares the common journey and moving-map areas.
        """
        points = self.get_session_route_points(session_id)
        if not points:
            return MapCacheWarmupResponse(
                success=False,
                cache_dir=str(self.cache_dir),
                message=t("map_cache_no_route", language),
            )

        max_tiles = max(1, settings.map_cache_warmup_max_tiles)
        max_maps = max(1, max_tiles // 9)
        rendered_maps = 0
        capped = len(points) > max_maps

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            rendered_maps += self._render_route_extent(points, map_style)

            samples = _sample_points(points, max(0, max_maps - rendered_maps))
            for point in samples:
                rendered_maps += self._render_moving_window(point, map_style)

            return MapCacheWarmupResponse(
                success=True,
                cache_dir=str(self.cache_dir),
                route_points=len(points),
                rendered_maps=rendered_maps,
                capped=capped,
                message=t("map_cache_partial" if capped else "map_cache_warmed", language),
            )
        except Exception as e:
            logger.warning("Map cache warmup failed: %s", e)
            return MapCacheWarmupResponse(
                success=False,
                cache_dir=str(self.cache_dir),
                route_points=len(points),
                rendered_maps=rendered_maps,
                capped=capped,
                message=f"{t('map_cache_failed', language)}: {e}",
            )

    def get_session_route_points(self, session_id: str) -> list[RoutePoint]:
        """Extract route points from the most relevant session GPS source."""
        primary = file_manager.get_primary_file(session_id)
        secondary = file_manager.get_secondary_file(session_id)
        source = secondary or primary
        if source is None:
            return []

        path = Path(source.file_path)
        file_type = source.file_type

        if file_type == "video" and getattr(source.video_metadata, "has_dji_meta", False):
            return _points_from_dji_meta(path)
        if file_type == "srt":
            return _points_from_srt(path)
        if file_type == "gpx":
            return _points_from_gpx(path)
        if file_type == "fit":
            return _points_from_external_timeseries(path)
        if file_type == "video":
            return _points_from_gopro_video(path)
        return []

    def _render_route_extent(self, points: list[RoutePoint], map_style: str) -> int:
        from gopro_overlay.geo import MapRenderer, MapStyler
        from gopro_overlay.vendor import geotiler

        min_lat, min_lon, max_lat, max_lon = _bounds(points)
        if math.isclose(min_lat, max_lat) and math.isclose(min_lon, max_lon):
            return self._render_moving_window(points[0], map_style)

        route_map = geotiler.Map(extent=(min_lon, min_lat, max_lon, max_lat), size=(512, 512))
        if route_map.zoom > 18:
            route_map.zoom = 18
        with MapRenderer(self.cache_dir, MapStyler()).open(map_style) as renderer:
            renderer(route_map)
        return 1

    def _render_moving_window(self, point: RoutePoint, map_style: str) -> int:
        from gopro_overlay.geo import MapRenderer, MapStyler
        from gopro_overlay.vendor import geotiler

        moving_map = geotiler.Map(center=(point.lon, point.lat), zoom=16, size=(384, 384))
        with MapRenderer(self.cache_dir, MapStyler()).open(map_style) as renderer:
            renderer(moving_map)
        return 1


def _sample_points(points: list[RoutePoint], limit: int) -> list[RoutePoint]:
    if limit <= 0 or not points:
        return []
    if len(points) <= limit:
        return points
    if limit == 1:
        return [points[len(points) // 2]]
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def _bounds(points: list[RoutePoint]) -> tuple[float, float, float, float]:
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    return min(lats), min(lons), max(lats), max(lons)


def _points_from_gpx(path: Path) -> list[RoutePoint]:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return []

    points = []
    for elem in root.iter():
        if elem.tag.endswith("trkpt"):
            try:
                points.append(RoutePoint(lat=float(elem.attrib["lat"]), lon=float(elem.attrib["lon"])))
            except (KeyError, ValueError):
                continue
    return points


def _points_from_srt(path: Path) -> list[RoutePoint]:
    try:
        from gpstitch.services.srt_parser import parse_srt

        return [RoutePoint(lat=p.lat, lon=p.lon) for p in parse_srt(path)]
    except Exception:
        return []


def _points_from_dji_meta(path: Path) -> list[RoutePoint]:
    try:
        from gpstitch.services.dji_meta_parser import parse_dji_meta_file

        return [RoutePoint(lat=p.lat, lon=p.lon) for p in parse_dji_meta_file(path)]
    except Exception:
        return []


def _points_from_external_timeseries(path: Path) -> list[RoutePoint]:
    try:
        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        timeseries = load_external(path, units)
        return _points_from_timeseries(timeseries)
    except Exception:
        return []


def _points_from_gopro_video(path: Path) -> list[RoutePoint]:
    try:
        from gopro_overlay.ffmpeg import FFMPEG
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro
        from gopro_overlay.loading import GoproLoader
        from gopro_overlay.units import units

        loaded = GoproLoader(FFMPEGGoPro(FFMPEG()), units).load(path)
        return _points_from_timeseries(loaded.framemeta)
    except Exception:
        return []


def _points_from_timeseries(timeseries) -> list[RoutePoint]:
    points = []
    for entry in timeseries.items():
        point = getattr(entry, "point", None)
        if point is None:
            continue
        lat = getattr(point, "lat", None)
        lon = getattr(point, "lon", None)
        if lat is None or lon is None:
            continue
        points.append(RoutePoint(lat=float(lat), lon=float(lon)))
    return points


map_cache_service = MapCacheService()
