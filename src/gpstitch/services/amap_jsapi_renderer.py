"""AMap JSAPI snapshot rendering for backend video jobs."""

from __future__ import annotations

import hashlib
import json
import logging
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
            "center": {"lat": float(lat), "lon": float(lon)},
            "current": {"lat": float(lat), "lon": float(lon)},
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
        options = {
            "kind": "journey",
            "size": int(size),
            "zoom": 16,
            "center": {"lat": float(current[0]), "lon": float(current[1])},
            "current": {"lat": float(current[0]), "lon": float(current[1])},
            "route": [{"lat": float(lat), "lon": float(lon)} for lat, lon in route],
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

    function toPair(location) {{
      if (Array.isArray(location)) return [location[0], location[1]];
      if (location && typeof location.getLng === 'function' && typeof location.getLat === 'function') {{
        return [location.getLng(), location.getLat()];
      }}
      return [location.lng, location.lat];
    }}

    async function convertPoints(AMap, points) {{
      if (!points.length) return [];
      const converted = [];
      for (let i = 0; i < points.length; i += 40) {{
        const batch = points.slice(i, i + 40).map(point => [point.lon, point.lat]);
        const locations = await new Promise((resolve, reject) => {{
          AMap.convertFrom(batch, 'gps', (status, result) => {{
            if (status === 'complete' && result && result.info === 'ok' && Array.isArray(result.locations)) {{
              resolve(result.locations);
            }} else {{
              reject(new Error((result && result.info) || 'AMap coordinate conversion failed'));
            }}
          }});
        }});
        for (const location of locations) converted.push(toPair(location));
      }}
      return converted;
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

        const current = options.current ? (await convertPoints(AMap, [options.current]))[0] : null;
        const route = await convertPoints(AMap, options.route || []);
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


def _rgb(value: tuple[int, int, int]) -> str:
    r, g, b = value
    return f"#{_clamp_color(r):02x}{_clamp_color(g):02x}{_clamp_color(b):02x}"


def _clamp_color(value: int) -> int:
    return max(0, min(255, int(value)))


def safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
