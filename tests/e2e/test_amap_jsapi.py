"""E2E coverage for AMap JSAPI UI integration with mocked provider APIs."""

import pytest
from playwright.sync_api import Page, expect


MOCK_AMAP_LOADER = """
window.AMapLoader = {
  load: function () {
    function Map(container, options) {
      this.container = container;
      this.options = options || {};
      this.add = function () {};
      this.setFitView = function () {};
      this.setCenter = function () {};
      this.setZoom = function () {};
      this.destroy = function () {};
    }
    function Polyline(options) { this.options = options || {}; }
    function Marker(options) { this.options = options || {}; }
    return Promise.resolve({
      Map,
      Polyline,
      Marker,
      convertFrom: function (coords, type, callback) {
        window.__amapConvertBatches = (window.__amapConvertBatches || 0) + 1;
        callback('complete', {
          info: 'ok',
          locations: coords.map(function (coord) {
            return {
              getLng: function () { return coord[0] + 0.001; },
              getLat: function () { return coord[1] + 0.001; }
            };
          })
        });
      }
    });
  }
};
"""


@pytest.mark.e2e
def test_amap_settings_save_and_validate_with_mock_loader(page: Page, base_url: str, live_server):
    page.add_init_script("localStorage.setItem('gpstitch_language', 'en');")
    page.request.delete(f"{base_url}/api/settings/amap")
    page.route(
        "https://webapi.amap.com/loader.js",
        lambda route: route.fulfill(status=200, content_type="application/javascript", body=MOCK_AMAP_LOADER),
    )

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator("#map-style").select_option("amap-jsapi")
    expect(page.locator("#amap-settings-panel")).to_be_visible()

    page.locator("#amap-key-input").fill("mock-key")
    page.locator("#amap-security-input").fill("mock-security")
    page.locator("#amap-save-btn").click()
    expect(page.locator("#amap-settings-status")).to_contain_text("Validation Required")

    page.locator("#amap-validate-btn").click()
    expect(page.locator("#amap-settings-status")).to_contain_text("Validated", timeout=10000)
    expect(page.locator("#amap-key-input")).to_have_value("")
    expect(page.locator("#amap-security-input")).to_have_value("")
    page.request.delete(f"{base_url}/api/settings/amap")


@pytest.mark.e2e
def test_amap_provider_overlays_two_preview_widgets(page: Page, base_url: str, live_server):
    page.add_init_script("localStorage.setItem('gpstitch_language', 'en');")
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate(MOCK_AMAP_LOADER)

    widget_count = page.evaluate(
        """async () => {
            const layer = document.createElement('div');
            document.body.appendChild(layer);
            const provider = new window.AMapProvider();
            await provider.render({
                layer,
                runtimeConfig: {
                    configured: true,
                    validated: true,
                    key: 'mock-key',
                    security_js_code: 'mock-security',
                    key_fingerprint: 'mock'
                },
                context: {
                    canvas_width: 1920,
                    canvas_height: 1080,
                    route_points: [
                        { lat: 30.0, lon: 120.0 },
                        { lat: 30.1, lon: 120.1 }
                    ],
                    map_widgets: [
                        { name: 'moving_map', type: 'moving_map', x: 1644, y: 100, width: 256, height: 256, zoom: 16, corner_radius: 35 },
                        { name: 'journey_map', type: 'journey_map', x: 1644, y: 376, width: 256, height: 256, zoom: 16, corner_radius: 35 }
                    ]
                },
                imageMetrics: { left: 0, top: 0, width: 1920, height: 1080 },
                frameTimeMs: 500,
                durationMs: 1000
            });
            return {
                widgets: layer.querySelectorAll('.amap-widget').length,
                batches: window.__amapConvertBatches
            };
        }"""
    )

    assert widget_count == {"widgets": 2, "batches": 1}
