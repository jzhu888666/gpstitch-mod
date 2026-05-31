"""AMap JSAPI snapshot rendering for backend video jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from gpstitch.config import settings
from gpstitch.models.schemas import AMapRuntimeConfigResponse
from gpstitch.services.amap_settings import AMAP_JSAPI_VERSION

logger = logging.getLogger(__name__)

MOVING_MAP_GRID_PIXELS = 16
DEFAULT_MARKER_RADIUS = 7
DEFAULT_MARKER_OUTLINE_WIDTH = 2


class AMapRenderError(RuntimeError):
    """Raised when backend AMap JSAPI rendering cannot produce a snapshot."""


@dataclass(frozen=True)
class AMapSnapshot:
    image: Image.Image
    metadata: dict[str, Any]


class AMapJSAPISnapshotRenderer:
    """Render AMap JSAPI maps to PIL images through a headless browser."""

    def __init__(
        self,
        runtime_config: AMapRuntimeConfigResponse,
        cache_dir: Path | None = None,
        timeout_ms: int = 20000,
        max_memory_snapshots: int = 128,
    ) -> None:
        if not runtime_config.configured or not runtime_config.validated:
            raise AMapRenderError("AMap credentials must be configured and validated before video rendering.")
        if not runtime_config.key or not runtime_config.security_js_code:
            raise AMapRenderError("AMap runtime key and security JS code are required for video rendering.")

        self.runtime_config = runtime_config
        self.timeout_ms = timeout_ms
        self.max_memory_snapshots = max(0, int(max_memory_snapshots))
        self.cache_dir = cache_dir or settings.map_cache_dir / "amap" / "render-snapshots"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: OrderedDict[str, AMapSnapshot] = OrderedDict()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def close(self) -> None:
        for obj in (self._context, self._browser):
            if obj is None:
                continue
            try:
                obj.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def render_moving(
        self,
        *,
        lat: float,
        lon: float,
        route: list[tuple[float, float]] | None = None,
        size: int,
        zoom: int,
        rotation_degrees: float | None = None,
        line_fill: tuple[int, int, int] = (31, 143, 255),
        line_width: int = 5,
        marker_fill: tuple[int, int, int] = (0, 0, 255),
        marker_outline: tuple[int, int, int] = (0, 0, 0),
    ) -> Image.Image:
        current = _to_amap_point(lat, lon)
        route = _sample_route(route or [], 600)
        output_size = int(size)
        render_size = _moving_backing_size(output_size)
        center = _quantize_point(current, int(zoom), MOVING_MAP_GRID_PIXELS)
        options = {
            "kind": "moving-base",
            "size": render_size,
            "zoom": int(zoom),
            "center": center,
            "route": [],
            "drawMarker": False,
        }
        snapshot = self._render_cached_snapshot(options)
        frame = snapshot.image.copy()
        if route:
            _draw_route_line(
                frame,
                [
                    _project_point(_to_amap_point(route_lat, route_lon), center, int(zoom), render_size)
                    for route_lat, route_lon in route
                ],
                line_fill,
                line_width,
            )
        marker_xy = _project_point(current, center, int(zoom), render_size)
        frame = _center_image_on_point(frame, marker_xy)
        if rotation_degrees is not None:
            frame = frame.rotate(float(rotation_degrees) % 360, resample=Image.BILINEAR)
        frame = _center_crop(frame, output_size)
        _draw_marker(frame, _image_center(frame), marker_fill, marker_outline)
        return frame

    def render_journey(
        self,
        *,
        route: list[tuple[float, float]],
        current: tuple[float, float],
        size: int,
        rotation_degrees: float | None = None,
        line_fill: tuple[int, int, int] = (31, 143, 255),
        line_width: int = 5,
        marker_fill: tuple[int, int, int] = (0, 0, 255),
        marker_outline: tuple[int, int, int] = (0, 0, 0),
    ) -> Image.Image:
        route = _sample_route(route, 600)
        output_size = int(size)
        render_size = _moving_backing_size(output_size) if rotation_degrees is not None else output_size
        current_point = _to_amap_point(current[0], current[1])
        options = {
            "kind": "journey-base",
            "size": render_size,
            "zoom": 16,
            "route": [_to_amap_point(lat, lon) for lat, lon in route],
            "lineFill": _rgb(line_fill),
            "lineWidth": int(line_width),
            "fitPadding": [round(output_size / 2)] * 4 if rotation_degrees is not None else [0, 0, 0, 0],
            "drawMarker": False,
        }
        snapshot = self._render_cached_snapshot(options)
        center = snapshot.metadata.get("center")
        zoom = snapshot.metadata.get("zoom")
        frame = snapshot.image.copy()
        if _valid_amap_point(center) and isinstance(zoom, int | float):
            marker_xy = _project_point(current_point, center, float(zoom), render_size)
        else:
            marker_xy = _image_center(frame)
        if rotation_degrees is not None:
            frame = frame.rotate(
                float(rotation_degrees) % 360,
                resample=Image.BILINEAR,
                center=marker_xy,
                fillcolor=(0, 0, 0, 0),
            )
            frame = _crop_around_point(frame, marker_xy, output_size)
            _draw_marker(frame, _image_center(frame), marker_fill, marker_outline)
            return frame
        _draw_marker(frame, marker_xy, marker_fill, marker_outline)
        return frame

    def _render_cached(self, options: dict[str, Any]) -> Image.Image:
        return self._render_cached_snapshot(options).image

    def _render_cached_snapshot(self, options: dict[str, Any]) -> AMapSnapshot:
        cache_key = self._cache_key(options)
        memory_snapshot = self._get_memory_snapshot(cache_key)
        if memory_snapshot is not None:
            return memory_snapshot

        target = self.cache_dir / f"{cache_key}.png"
        metadata_target = self.cache_dir / f"{cache_key}.json"
        if target.exists() and metadata_target.exists():
            metadata = _read_json(metadata_target)
            snapshot = AMapSnapshot(Image.open(target).convert("RGBA"), metadata)
            self._store_memory_snapshot(cache_key, snapshot)
            return snapshot

        snapshot = self._render_snapshot(options)
        fd, temp_name = tempfile.mkstemp(prefix=f"{cache_key}.", suffix=".png", dir=self.cache_dir)
        os.close(fd)
        temp_path = Path(temp_name)
        metadata_temp_path = self.cache_dir / f"{cache_key}.json.tmp"
        try:
            snapshot.image.save(temp_path, format="PNG")
            metadata_temp_path.write_text(
                json.dumps(snapshot.metadata, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.replace(target)
            metadata_temp_path.replace(metadata_target)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if metadata_temp_path.exists():
                metadata_temp_path.unlink(missing_ok=True)
        self._store_memory_snapshot(cache_key, snapshot)
        return snapshot

    def _get_memory_snapshot(self, cache_key: str) -> AMapSnapshot | None:
        if self.max_memory_snapshots <= 0:
            return None
        snapshot = self._memory_cache.get(cache_key)
        if snapshot is not None:
            self._memory_cache.move_to_end(cache_key)
        return snapshot

    def _store_memory_snapshot(self, cache_key: str, snapshot: AMapSnapshot) -> None:
        if self.max_memory_snapshots <= 0:
            return
        self._memory_cache[cache_key] = snapshot
        self._memory_cache.move_to_end(cache_key)
        while len(self._memory_cache) > self.max_memory_snapshots:
            self._memory_cache.popitem(last=False)

    def _render_snapshot(self, options: dict[str, Any]) -> AMapSnapshot:
        page = self._ensure_page()
        try:
            result = page.evaluate("async (options) => await window.renderAmapSnapshot(options)", options)
            if not result or not result.get("ok"):
                raise AMapRenderError(result.get("error") if result else "AMap snapshot rendering failed.")
            png_bytes = page.locator("#map").screenshot(type="png", timeout=self.timeout_ms)
        except AMapRenderError:
            raise
        except Exception as e:
            raise AMapRenderError(f"AMap snapshot rendering failed: {e}") from e
        return AMapSnapshot(_image_from_png(png_bytes), result.get("metadata") or {})

    def _ensure_page(self):
        if self._page is not None:
            return self._page

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise AMapRenderError(
                "Python Playwright is required for AMap video rendering. "
                "Install project dependencies and browser support before rendering with AMap."
            ) from e

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as first_error:
            logger.debug("Bundled Playwright Chromium launch failed; trying system Microsoft Edge: %s", first_error)
            try:
                self._browser = self._playwright.chromium.launch(channel="msedge", headless=True)
            except Exception as edge_error:
                raise AMapRenderError(
                    "Unable to launch a headless browser for AMap video rendering. "
                    "Install Playwright browsers or ensure Microsoft Edge is available."
                ) from edge_error

        self._context = self._browser.new_context(
            viewport={"width": 1024, "height": 1024},
            device_scale_factor=1,
        )
        self._context.route("**/gpstitch-amap-renderer", lambda route: route.fulfill(
            status=200,
            content_type="text/html; charset=utf-8",
            body=_renderer_html(self.runtime_config),
        ))
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        self._page.goto("http://127.0.0.1/gpstitch-amap-renderer", wait_until="domcontentloaded")
        return self._page

    def _cache_key(self, options: dict[str, Any]) -> str:
        payload = {
            "version": AMAP_JSAPI_VERSION,
            "renderer": "gcj02-route-heading-v3",
            "fingerprint": self.runtime_config.key_fingerprint,
            "options": options,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def _renderer_html(runtime_config: AMapRuntimeConfigResponse) -> str:
    key = json.dumps(runtime_config.key)
    security = json.dumps(runtime_config.security_js_code)
    version = json.dumps(AMAP_JSAPI_VERSION)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body, #map {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; }}
    .amap-logo,
    .amap-copyright,
    .amap-mcode,
    .amap-scalecontrol,
    .amap-controlbar {{
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }}
    .amap-current-marker {{
      display: block;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--marker-fill, #006dff);
      border: 2px solid var(--marker-outline, #000);
      box-shadow: 0 1px 4px rgba(0,0,0,.35);
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    window._AMapSecurityConfig = {{ securityJsCode: {security} }};
  </script>
  <script src="https://webapi.amap.com/loader.js"></script>
  <script>
    const AMAP_KEY = {key};
    const AMAP_VERSION = {version};
    let amapPromise = null;
    let activeMap = null;

    function sleep(ms) {{
      return new Promise(resolve => setTimeout(resolve, ms));
    }}

    async function loadAmap() {{
      if (!amapPromise) {{
        amapPromise = AMapLoader.load({{
          key: AMAP_KEY,
          version: AMAP_VERSION,
          plugins: []
        }});
      }}
      return amapPromise;
    }}

    function toLngLat(point) {{
      return [point.lng, point.lat];
    }}

    function fromLngLat(location) {{
      if (Array.isArray(location)) return {{ lng: location[0], lat: location[1] }};
      if (location && typeof location.getLng === 'function' && typeof location.getLat === 'function') {{
        return {{ lng: location.getLng(), lat: location.getLat() }};
      }}
      return {{ lng: location.lng, lat: location.lat }};
    }}

    function waitMapComplete(map) {{
      return new Promise(resolve => {{
        let done = false;
        const finish = () => {{
          if (done) return;
          done = true;
          resolve();
        }};
        map.on('complete', finish);
        setTimeout(finish, 1500);
      }});
    }}

    window.renderAmapSnapshot = async function(options) {{
      try {{
        const mapEl = document.getElementById('map');
        mapEl.style.width = `${{Math.max(1, options.size || 256)}}px`;
        mapEl.style.height = `${{Math.max(1, options.size || 256)}}px`;
        document.documentElement.style.width = mapEl.style.width;
        document.documentElement.style.height = mapEl.style.height;
        document.body.style.width = mapEl.style.width;
        document.body.style.height = mapEl.style.height;
        mapEl.style.setProperty('--marker-fill', options.markerFill || '#006dff');
        mapEl.style.setProperty('--marker-outline', options.markerOutline || '#000000');

        const AMap = await loadAmap();
        if (activeMap) {{
          activeMap.destroy();
          activeMap = null;
        }}

        const explicitCenter = options.center ? toLngLat(options.center) : null;
        const current = options.current ? toLngLat(options.current) : null;
        const route = (options.route || []).map(toLngLat);
        const center = explicitCenter || current || route[0] || [116.397428, 39.90923];

        const map = new AMap.Map(mapEl, {{
          viewMode: '2D',
          resizeEnable: false,
          animateEnable: false,
          zoom: options.zoom || 16,
          center
        }});
        activeMap = map;

        const overlays = [];
        if (route.length > 1) {{
          const polyline = new AMap.Polyline({{
            path: route,
            showDir: false,
            strokeColor: options.lineFill || '#1f8fff',
            strokeOpacity: 0.9,
            strokeWeight: Math.max(1, options.lineWidth || 5),
            lineJoin: 'round',
            zIndex: 20
          }});
          map.add(polyline);
          overlays.push(polyline);
        }}
        if (current && options.drawMarker !== false) {{
          const marker = new AMap.Marker({{
            position: current,
            anchor: 'center',
            content: '<span class="amap-current-marker"></span>',
            zIndex: 40
          }});
          map.add(marker);
          overlays.push(marker);
        }}

        if (String(options.kind || '').startsWith('journey') && overlays.length > 0) {{
          const fitPadding = Array.isArray(options.fitPadding) ? options.fitPadding : [0, 0, 0, 0];
          map.setFitView(overlays, false, fitPadding);
        }} else if (current) {{
          map.setCenter(current);
          map.setZoom(options.zoom || 16);
        }} else if (explicitCenter) {{
          map.setCenter(explicitCenter);
          map.setZoom(options.zoom || 16);
        }}

        await waitMapComplete(map);
        await sleep(650);
        return {{
          ok: true,
          metadata: {{
            center: fromLngLat(map.getCenter()),
            zoom: map.getZoom()
          }}
        }};
      }} catch (error) {{
        return {{ ok: false, error: String(error && error.message ? error.message : error) }};
      }}
    }};
  </script>
</body>
</html>"""


def _image_from_png(png_bytes: bytes) -> Image.Image:
    from io import BytesIO

    return Image.open(BytesIO(png_bytes)).convert("RGBA")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _moving_backing_size(size: int) -> int:
    return int(math.sqrt((int(size) ** 2) * 2))


def _center_crop(image: Image.Image, size: int) -> Image.Image:
    size = int(size)
    if image.size == (size, size):
        return image
    if image.width < size or image.height < size:
        padded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        padded.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
        return padded
    left = round((image.width - size) / 2)
    top = round((image.height - size) / 2)
    return image.crop((left, top, left + size, top + size))


def _crop_around_point(image: Image.Image, point: tuple[int, int], size: int) -> Image.Image:
    size = int(size)
    left = int(round(point[0] - size / 2))
    top = int(round(point[1] - size / 2))
    right = left + size
    bottom = top + size
    src_left = max(0, left)
    src_top = max(0, top)
    src_right = min(image.width, right)
    src_bottom = min(image.height, bottom)
    cropped = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if src_left < src_right and src_top < src_bottom:
        cropped.alpha_composite(
            image.crop((src_left, src_top, src_right, src_bottom)),
            (src_left - left, src_top - top),
        )
    return cropped


def _center_image_on_point(image: Image.Image, point: tuple[int, int]) -> Image.Image:
    center = _image_center(image)
    dx = center[0] - int(point[0])
    dy = center[1] - int(point[1])
    if dx == 0 and dy == 0:
        return image

    shifted = Image.new("RGBA", image.size, (0, 0, 0, 0))
    src_left = max(0, -dx)
    src_top = max(0, -dy)
    src_right = min(image.width, image.width - dx)
    src_bottom = min(image.height, image.height - dy)
    if src_left < src_right and src_top < src_bottom:
        shifted.alpha_composite(
            image.crop((src_left, src_top, src_right, src_bottom)),
            (max(0, dx), max(0, dy)),
        )
    return shifted


def _image_center(image: Image.Image) -> tuple[int, int]:
    return (round(image.width / 2), round(image.height / 2))


def _sample_route(route: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    if len(route) <= limit:
        return route
    step = (len(route) - 1) / max(1, limit - 1)
    return [route[round(i * step)] for i in range(limit)]


def _to_amap_point(lat: float, lon: float) -> dict[str, float]:
    gcj_lat, gcj_lon = _wgs84_to_gcj02(float(lat), float(lon))
    return {"lat": gcj_lat, "lng": gcj_lon}


def _valid_amap_point(point: Any) -> bool:
    return isinstance(point, dict) and isinstance(point.get("lat"), int | float) and isinstance(point.get("lng"), int | float)


def _quantize_point(point: dict[str, float], zoom: int, grid_pixels: int) -> dict[str, float]:
    x, y = _point_to_world_pixel(point, zoom)
    grid = max(1, int(grid_pixels))
    return _world_pixel_to_point(round(x / grid) * grid, round(y / grid) * grid, zoom)


def _project_point(
    point: dict[str, float],
    center: dict[str, float],
    zoom: float,
    size: int,
) -> tuple[int, int]:
    point_x, point_y = _point_to_world_pixel(point, zoom)
    center_x, center_y = _point_to_world_pixel(center, zoom)
    return (round(size / 2 + point_x - center_x), round(size / 2 + point_y - center_y))


def _point_to_world_pixel(point: dict[str, float], zoom: float) -> tuple[float, float]:
    lng = float(point["lng"])
    lat = max(-85.05112878, min(85.05112878, float(point["lat"])))
    scale = 256.0 * (2.0 ** float(zoom))
    x = (lng + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)) * scale
    return x, y


def _world_pixel_to_point(x: float, y: float, zoom: float) -> dict[str, float]:
    scale = 256.0 * (2.0 ** float(zoom))
    lng = x / scale * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / scale))))
    return {"lat": lat, "lng": lng}


def _draw_marker(
    image: Image.Image,
    position: tuple[int, int],
    fill: tuple[int, ...],
    outline: tuple[int, ...],
    radius: int = DEFAULT_MARKER_RADIUS,
    outline_width: int = DEFAULT_MARKER_OUTLINE_WIDTH,
) -> None:
    draw = ImageDraw.Draw(image)
    x, y = position
    outline_color = _rgba(outline)
    fill_color = _rgba(fill)
    outer_radius = radius + max(0, outline_width)
    draw.ellipse(
        (x - outer_radius, y - outer_radius, x + outer_radius, y + outer_radius),
        fill=outline_color,
    )
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill_color)


def _draw_route_line(
    image: Image.Image,
    points: list[tuple[int, int]],
    fill: tuple[int, ...],
    width: int,
) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(image)
    draw.line(points, fill=_rgba((*fill[:3], 230)), width=max(1, int(width)), joint="curve")


def _wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS84/GPS coordinates to GCJ-02 coordinates used by AMap."""
    if _outside_china(lat, lon):
        return lat, lon

    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrt_magic * math.cos(radlat) * math.pi)
    return lat + dlat, lon + dlon


def _outside_china(lat: float, lon: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _rgb(value: tuple[int, ...]) -> str:
    r, g, b = value[:3]
    return f"#{_clamp_color(r):02x}{_clamp_color(g):02x}{_clamp_color(b):02x}"


def _rgba(value: tuple[int, ...]) -> tuple[int, int, int, int]:
    r, g, b = value[:3]
    a = value[3] if len(value) > 3 else 255
    return (_clamp_color(r), _clamp_color(g), _clamp_color(b), _clamp_color(a))


def _clamp_color(value: int) -> int:
    return max(0, min(255, int(value)))


def safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
