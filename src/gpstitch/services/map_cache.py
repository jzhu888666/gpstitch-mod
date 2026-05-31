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


@dataclass(frozen=True)
class MovingMapWarmupSpec:
    size: int = 256
    zoom: int = 16

    @property
    def render_size(self) -> int:
        return int(math.sqrt((self.size**2) * 2))

    @property
    def estimated_tile_count(self) -> int:
        tiles_per_axis = max(1, math.ceil(self.render_size / 256) + 1)
        return tiles_per_axis * tiles_per_axis


@dataclass(frozen=True)
class MapWarmupPlan:
    moving_maps: tuple[MovingMapWarmupSpec, ...] = (MovingMapWarmupSpec(),)
    warm_journey: bool = True
    journey_size: int = 256

    @property
    def uses_maps(self) -> bool:
        return self.warm_journey or bool(self.moving_maps)


class MapCacheService:
    """Warm and expose the map cache used by previews and render subprocesses."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or settings.map_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def warm_session_cache(
        self,
        session_id: str,
        map_style: str = "osm",
        layout: str | None = None,
        layout_xml_path: str | None = None,
        language: str | None = None,
        max_tiles: int | None = None,
    ) -> MapCacheWarmupResponse:
        """Warm map cache tiles for a session route.

        This is intentionally bounded. Preview/render still lazily fetch missing
        tiles, but this prepares the common journey and moving-map areas using
        the actual map widget sizes from the selected layout.
        """
        plan = _warmup_plan_for_layout(layout, layout_xml_path, language)
        if not plan.uses_maps:
            return MapCacheWarmupResponse(
                success=True,
                cache_dir=str(self.cache_dir),
                message=t("map_cache_warmed", language),
            )

        points = self.get_session_route_points(session_id)
        if not points:
            return MapCacheWarmupResponse(
                success=False,
                cache_dir=str(self.cache_dir),
                message=t("map_cache_no_route", language),
            )

        tile_limit = settings.map_cache_warmup_max_tiles if max_tiles is None else max_tiles
        tile_limit = max(1, tile_limit)
        rendered_maps = 0
        samples: list[RoutePoint] = []

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            remaining_tiles = tile_limit
            if plan.warm_journey:
                rendered_maps += self._render_route_extent(points, map_style, plan.journey_size)
                remaining_tiles = max(0, remaining_tiles - _estimate_square_tile_count(plan.journey_size))

            moving_tile_cost = sum(spec.estimated_tile_count for spec in plan.moving_maps)
            sample_limit = max(0, remaining_tiles // max(1, moving_tile_cost)) if plan.moving_maps else 0
            distinct_moving_points = _distinct_moving_window_points(points, plan.moving_maps)
            samples = _sample_points(distinct_moving_points, sample_limit)
            for point in samples:
                for spec in plan.moving_maps:
                    rendered_maps += self._render_moving_window(point, map_style, spec)

            capped = bool(plan.moving_maps) and len(samples) < len(distinct_moving_points)

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
                capped=bool(samples) and len(samples) < len(points),
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

    def _render_route_extent(self, points: list[RoutePoint], map_style: str, size: int = 256) -> int:
        from gopro_overlay.geo import MapRenderer, MapStyler
        from gopro_overlay.vendor import geotiler

        min_lat, min_lon, max_lat, max_lon = _bounds(points)
        if math.isclose(min_lat, max_lat) and math.isclose(min_lon, max_lon):
            return self._render_moving_window(points[0], map_style)

        route_map = geotiler.Map(extent=(min_lon, min_lat, max_lon, max_lat), size=(size, size))
        if route_map.zoom > 18:
            route_map.zoom = 18
        with MapRenderer(self.cache_dir, MapStyler()).open(map_style) as renderer:
            renderer(route_map)
        return 1

    def _render_moving_window(
        self,
        point: RoutePoint,
        map_style: str,
        spec: MovingMapWarmupSpec = MovingMapWarmupSpec(),
    ) -> int:
        from gopro_overlay.geo import MapRenderer, MapStyler
        from gopro_overlay.vendor import geotiler

        render_size = spec.render_size
        moving_map = geotiler.Map(center=(point.lon, point.lat), zoom=spec.zoom, size=(render_size, render_size))
        with MapRenderer(self.cache_dir, MapStyler()).open(map_style) as renderer:
            renderer(moving_map)
        return 1


def _warmup_plan_for_layout(
    layout: str | None,
    layout_xml_path: str | None = None,
    language: str | None = None,
) -> MapWarmupPlan:
    root = _read_layout_root(layout, layout_xml_path, language)
    if root is None:
        return MapWarmupPlan()

    moving_specs: list[MovingMapWarmupSpec] = []
    journey_sizes: list[int] = []
    for elem in root.iter("component"):
        component_type = elem.attrib.get("type")
        if component_type in {"moving_map", "moving_journey_map"}:
            moving_specs.append(
                MovingMapWarmupSpec(
                    size=_int_attr(elem, "size", 256),
                    zoom=_int_attr(elem, "zoom", 16),
                )
            )
        elif component_type == "journey_map":
            journey_sizes.append(_int_attr(elem, "size", 256))

    return MapWarmupPlan(
        moving_maps=tuple(dict.fromkeys(moving_specs)),
        warm_journey=bool(journey_sizes),
        journey_size=max(journey_sizes, default=256),
    )


def _read_layout_root(
    layout: str | None,
    layout_xml_path: str | None = None,
    language: str | None = None,
) -> ET.Element | None:
    try:
        if layout_xml_path:
            return ET.parse(layout_xml_path).getroot()
        if not layout:
            return None
        from gpstitch.services.renderer import _resolve_layout_path

        return ET.parse(_resolve_layout_path(layout, language=language)).getroot()
    except Exception as e:
        logger.debug("Could not read map warmup layout %s/%s: %s", layout, layout_xml_path, e)
        return None


def _int_attr(elem: ET.Element, attr: str, default: int) -> int:
    try:
        return int(elem.attrib.get(attr, default))
    except (TypeError, ValueError):
        return default


def _estimate_square_tile_count(size: int) -> int:
    tiles_per_axis = max(1, math.ceil(size / 256) + 1)
    return tiles_per_axis * tiles_per_axis


def _distinct_moving_window_points(
    points: list[RoutePoint],
    specs: tuple[MovingMapWarmupSpec, ...],
) -> list[RoutePoint]:
    selected: list[RoutePoint] = []
    seen = set()
    for point in points:
        key = tuple(_moving_window_key(point, spec) for spec in specs)
        if key in seen:
            continue
        seen.add(key)
        selected.append(point)
    return selected


def _moving_window_key(point: RoutePoint, spec: MovingMapWarmupSpec):
    from gopro_overlay.vendor import geotiler
    from gopro_overlay.vendor.geotiler.map import _find_top_left_tile, _tile_coords

    render_size = spec.render_size
    moving_map = geotiler.Map(center=(point.lon, point.lat), zoom=spec.zoom, size=(render_size, render_size))
    coord, offset = _find_top_left_tile(moving_map)
    return (moving_map.zoom, tuple(_tile_coords(moving_map, coord, offset)))


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
