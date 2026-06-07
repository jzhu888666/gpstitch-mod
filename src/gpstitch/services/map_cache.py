"""Project-local map tile cache warmup helpers."""

from __future__ import annotations

import logging
import math
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from gpstitch.config import settings
from gpstitch.models.schemas import AMapMapWidget, AMapRenderContextResponse, AMapRoutePoint, MapCacheWarmupResponse
from gpstitch.services.amap_settings import (
    AMAP_JSAPI_VERSION,
    AMAP_PROVIDER,
    amap_settings_service,
    is_amap_style,
    normalize_amap_style,
)
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
        if is_amap_style(map_style):
            amap_style = normalize_amap_style(map_style)
            points = self.get_session_route_points(session_id)
            cache_key = self._write_amap_descriptor(
                session_id=session_id,
                points=points,
                widgets=self.get_layout_map_widgets(layout, layout_xml_path, language),
                layout=layout,
                map_style=amap_style,
            )
            return MapCacheWarmupResponse(
                success=True,
                cache_dir=str(self._amap_cache_dir()),
                route_points=len(points),
                rendered_maps=0,
                capped=False,
                provider=AMAP_PROVIDER,
                cache_key=cache_key,
                message=(
                    "AMap JS API base-map resources are managed by the browser/provider; "
                    "GPStitch prepared route overlay metadata only."
                ),
            )

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

    def build_amap_render_context(
        self,
        session_id: str,
        layout: str | None = None,
        frame_time_ms: int = 0,
        language: str | None = None,
        map_style: str | None = None,
    ) -> AMapRenderContextResponse:
        """Build browser-side AMap overlay context for the selected layout."""
        points = self.get_session_route_points(session_id)
        widgets = self.get_layout_map_widgets(layout, language=language)
        canvas_width, canvas_height = _layout_canvas_size(layout)
        sampled_points = _sample_points(points, settings.map_cache_warmup_max_tiles)
        amap_style = normalize_amap_style(map_style)
        cache_key = self._write_amap_descriptor(
            session_id=session_id,
            points=sampled_points,
            widgets=widgets,
            layout=layout,
            frame_time_ms=frame_time_ms,
            map_style=amap_style,
        )
        return AMapRenderContextResponse(
            success=True,
            provider=AMAP_PROVIDER,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            map_style=amap_style,
            route_points=[AMapRoutePoint(lat=p.lat, lon=p.lon) for p in sampled_points],
            map_widgets=widgets,
            cache_key=cache_key,
            message="AMap overlay context prepared.",
        )

    def get_layout_map_widgets(
        self,
        layout: str | None,
        layout_xml_path: str | None = None,
        language: str | None = None,
    ) -> list[AMapMapWidget]:
        """Return map widget rectangles from a layout XML."""
        root = _read_layout_root(layout, layout_xml_path, language)
        if root is None:
            return []
        widgets: list[AMapMapWidget] = []
        _collect_map_widgets(root, widgets)
        return widgets

    def clear_amap_cache(self) -> bool:
        """Clear AMap-specific GPStitch cache entries without touching tile caches."""
        cache_dir = self._amap_cache_dir()
        if not cache_dir.exists():
            return False
        shutil.rmtree(cache_dir)
        return True

    def _amap_cache_dir(self) -> Path:
        return self.cache_dir / "amap"

    def _write_amap_descriptor(
        self,
        *,
        session_id: str,
        points: list[RoutePoint],
        widgets: list[AMapMapWidget],
        layout: str | None,
        frame_time_ms: int = 0,
        map_style: str | None = None,
    ) -> str:
        cache_key = _amap_cache_key(
            session_id=session_id,
            points=points,
            widgets=widgets,
            layout=layout,
            frame_time_ms=frame_time_ms,
            map_style=map_style,
        )
        target_dir = self._amap_cache_dir() / "descriptors"
        target_dir.mkdir(parents=True, exist_ok=True)
        descriptor = {
            "provider": AMAP_PROVIDER,
            "amap_version": AMAP_JSAPI_VERSION,
            "session_id": session_id,
            "layout": layout,
            "frame_time_ms": frame_time_ms,
            "map_style": map_style or "amap-jsapi",
            "route_hash": _route_hash(points),
            "credential_fingerprint": amap_settings_service.cache_fingerprint(),
            "widgets": [w.model_dump() for w in widgets],
        }
        (target_dir / f"{cache_key}.json").write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return cache_key

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


def _collect_map_widgets(
    elem: ET.Element,
    widgets: list[AMapMapWidget],
    offset_x: int = 0,
    offset_y: int = 0,
) -> None:
    x = offset_x + _int_attr(elem, "x", 0)
    y = offset_y + _int_attr(elem, "y", 0)
    component_type = elem.attrib.get("type")
    if elem.tag == "component" and component_type in {"moving_map", "journey_map", "moving_journey_map"}:
        size = _int_attr(elem, "size", 256)
        widgets.append(
            AMapMapWidget(
                name=elem.attrib.get("name") or component_type,
                type=component_type,
                x=x,
                y=y,
                width=_int_attr(elem, "width", size),
                height=_int_attr(elem, "height", size),
                zoom=_int_attr(elem, "zoom", 16),
                corner_radius=_int_attr(elem, "corner_radius", _int_attr(elem, "cr", 0)),
                opacity=_float_attr(elem, "opacity", 0.7),
                rotate=_bool_attr(elem, "rotate", True),
                line_fill=_color_attr(elem, "fill", "#1f8fff"),
                line_width=_int_attr(elem, "line-width", 5),
            )
        )

    for child in elem:
        _collect_map_widgets(child, widgets, x, y)


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


def _layout_canvas_size(layout: str | None) -> tuple[int, int]:
    if not layout:
        return 1920, 1080
    try:
        from gpstitch.services.renderer import _parse_resolution

        return _parse_resolution(layout)
    except Exception:
        return 1920, 1080


def _int_attr(elem: ET.Element, attr: str, default: int) -> int:
    try:
        return int(elem.attrib.get(attr, default))
    except (TypeError, ValueError):
        return default


def _float_attr(elem: ET.Element, attr: str, default: float) -> float:
    try:
        return float(elem.attrib.get(attr, default))
    except (TypeError, ValueError):
        return default


def _bool_attr(elem: ET.Element, attr: str, default: bool) -> bool:
    raw = elem.attrib.get(attr)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _color_attr(elem: ET.Element, attr: str, default: str) -> str:
    raw = elem.attrib.get(attr)
    if not raw:
        return default
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) < 3:
        return default
    try:
        r, g, b = (max(0, min(255, int(float(part)))) for part in parts[:3])
    except ValueError:
        return default
    return f"#{r:02x}{g:02x}{b:02x}"


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


def _route_hash(points: list[RoutePoint]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(points)).encode("ascii"))
    for point in points:
        digest.update(f"|{point.lat:.7f},{point.lon:.7f}".encode("ascii"))
    return digest.hexdigest()[:16]


def _amap_cache_key(
    *,
    session_id: str,
    points: list[RoutePoint],
    widgets: list[AMapMapWidget],
    layout: str | None,
    frame_time_ms: int,
    map_style: str | None = None,
) -> str:
    digest = hashlib.sha256()
    digest.update(AMAP_PROVIDER.encode("ascii"))
    digest.update(AMAP_JSAPI_VERSION.encode("ascii"))
    digest.update(amap_settings_service.cache_fingerprint().encode("ascii"))
    digest.update(session_id.encode("utf-8"))
    digest.update(str(layout or "").encode("utf-8"))
    digest.update(str(map_style or "amap-jsapi").encode("utf-8"))
    digest.update(str(frame_time_ms).encode("ascii"))
    digest.update(_route_hash(points).encode("ascii"))
    for widget in widgets:
        digest.update(
            (
                f"|{widget.name}:{widget.type}:{widget.x}:{widget.y}:{widget.width}:{widget.height}:"
                f"{widget.zoom}:{widget.corner_radius}:{widget.opacity:.3f}:{widget.rotate}:"
                f"{widget.line_fill}:{widget.line_width}"
            ).encode("utf-8")
        )
    return digest.hexdigest()[:24]


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
