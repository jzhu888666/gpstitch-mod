"""AMap JSAPI snapshot rendering for backend video jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from gpstitch.config import settings
from gpstitch.models.schemas import AMapRuntimeConfigResponse
from gpstitch.services.amap_settings import AMAP_JSAPI_VERSION

logger = logging.getLogger(__name__)


class AMapRenderError(RuntimeError):
    """Raised when backend AMap JSAPI rendering cannot produce a snapshot."""


class AMapJSAPISnapshotRenderer:
    """Render AMap JSAPI maps to PIL images through a headless browser."""

    def __init__(
        self,
        runtime_config: AMapRuntimeConfigResponse,
        cache_dir: Path | None = None,
        timeout_ms: int = 20000,
    ) -> None:
        if not runtime_config.configured or not runtime_config.validated:
            raise AMapRenderError("AMap credentials must be configured and validated before video rendering.")
        if not runtime_config.key or not runtime_config.security_js_code:
            raise AMapRenderError("AMap runtime key and security JS code are required for video rendering.")

        self.runtime_config = runtime_config
        self.timeout_ms = timeout_ms
        self.cache_dir = cache_dir or settings.map_cache_dir / "amap" / "render-snapshots"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
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
        size: int,
        zoom: int,
        marker_fill: tuple[int, int, int] = (0, 0, 255),
        marker_outline: tuple[int, int, int] = (0, 0, 0),
    ) -> Image.Image:
        options = {
            "kind": "moving",
            "size": int(size),
            "zoom": int(zoom),
            "center": _to_amap_point(lat, lon),
            "current": _to_amap_point(lat, lon),
            "route": [],
            "markerFill": _rgb(marker_fill),
            "markerOutline": _rgb(marker_outline),
        }
        return self._render_cached(options)

    def render_journey(
        self,
        *,
        route: list[tuple[float, float]],
        current: tuple[float, float],
        size: int,
        line_fill: tuple[int, int, int] = (31, 143, 255),
        line_width: int = 5,
        marker_fill: tuple[int, int, int] = (0, 0, 255),
        marker_outline: tuple[int, int, int] = (0, 0, 0),
    ) -> Image.Image:
        route = _sample_route(route, 600)
        current_point = _to_amap_point(current[0], current[1])
        options = {
            "kind": "journey",
            "size": int(size),
            "zoom": 16,
            "center": current_point,
            "current": current_point,
            "route": [_to_amap_point(lat, lon) for lat, lon in route],
            "lineFill": _rgb(line_fill),
            "lineWidth": int(line_width),
            "markerFill": _rgb(marker_fill),
            "markerOutline": _rgb(marker_outline),
        }
        return self._render_cached(options)

    def _render_cached(self, options: dict[str, Any]) -> Image.Image:
        cache_key = self._cache_key(options)
        target = self.cache_dir / f"{cache_key}.png"
        if target.exists():
            return Image.open(target).convert("RGBA")

        image = self._render_snapshot(options)
        fd, temp_name = tempfile.mkstemp(prefix=f"{cache_key}.", suffix=".png", dir=self.cache_dir)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            image.save(temp_path, format="PNG")
            temp_path.replace(target)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        return image

    def _render_snapshot(self, options: dict[str, Any]) -> Image.Image:
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
        return _image_from_png(png_bytes)

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
            "renderer": "gcj02-local-v1",
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

        const current = options.current ? toLngLat(options.current) : null;
        const route = (options.route || []).map(toLngLat);
        const center = current || route[0] || [116.397428, 39.90923];

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
        if (current) {{
          const marker = new AMap.Marker({{
            position: current,
            anchor: 'center',
            content: '<span class="amap-current-marker"></span>',
            zIndex: 40
          }});
          map.add(marker);
          overlays.push(marker);
        }}

        if (options.kind === 'journey' && overlays.length > 0) {{
          map.setFitView(overlays, false, [16, 16, 16, 16]);
        }} else if (current) {{
          map.setCenter(current);
          map.setZoom(options.zoom || 16);
        }}

        await waitMapComplete(map);
        await sleep(650);
        return {{ ok: true }};
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


def _sample_route(route: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    if len(route) <= limit:
        return route
    step = (len(route) - 1) / max(1, limit - 1)
    return [route[round(i * step)] for i in range(limit)]


def _to_amap_point(lat: float, lon: float) -> dict[str, float]:
    gcj_lat, gcj_lon = _wgs84_to_gcj02(float(lat), float(lon))
    return {"lat": gcj_lat, "lng": gcj_lon}


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


def _rgb(value: tuple[int, int, int]) -> str:
    r, g, b = value
    return f"#{_clamp_color(r):02x}{_clamp_color(g):02x}{_clamp_color(b):02x}"


def _clamp_color(value: int) -> int:
    return max(0, min(255, int(value)))


def safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
