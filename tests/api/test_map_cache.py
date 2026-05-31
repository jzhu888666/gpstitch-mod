"""Tests for map cache API endpoints."""

import asyncio
import threading

from gpstitch.models.schemas import MapCacheWarmupRequest, MapCacheWarmupResponse


async def test_warm_map_cache_runs_warmup_outside_request_event_loop(monkeypatch, temp_dir):
    """geotiler may call asyncio.run(), so warmup must not execute in the request loop."""
    from gpstitch.api import map_cache

    request_thread_id = threading.get_ident()

    class WarmupService:
        warmup_thread_id: int | None = None

        def warm_session_cache(self, session_id, map_style, layout, language):
            self.warmup_thread_id = threading.get_ident()
            asyncio.run(asyncio.sleep(0))
            return MapCacheWarmupResponse(
                success=True,
                cache_dir=str(temp_dir / "maps"),
                route_points=2,
                rendered_maps=1,
                capped=False,
                message="warmed",
            )

    service = WarmupService()
    monkeypatch.setattr(map_cache.file_manager, "session_exists", lambda session_id: True)
    monkeypatch.setattr(map_cache, "map_cache_service", service)

    response = await map_cache.warm_map_cache(
        MapCacheWarmupRequest(session_id="session", map_style="osm", language="en")
    )

    assert response.success is True
    assert service.warmup_thread_id is not None
    assert service.warmup_thread_id != request_thread_id


def test_amap_cache_warmup_writes_only_descriptor_metadata(monkeypatch, temp_dir):
    from gpstitch.services.map_cache import AMapMapWidget, MapCacheService, RoutePoint

    service = MapCacheService(cache_dir=temp_dir / "maps")
    monkeypatch.setattr(
        service,
        "get_session_route_points",
        lambda session_id: [RoutePoint(lat=30.0, lon=120.0), RoutePoint(lat=30.1, lon=120.1)],
    )
    monkeypatch.setattr(
        service,
        "get_layout_map_widgets",
        lambda *args, **kwargs: [
            AMapMapWidget(name="moving_map", type="moving_map", x=100, y=100, width=256, height=256)
        ],
    )

    response = service.warm_session_cache("session", map_style="amap-jsapi", layout="default-1920x1080")

    assert response.success is True
    assert response.provider == "amap"
    assert response.rendered_maps == 0
    assert list((temp_dir / "maps" / "amap" / "descriptors").glob("*.json"))
    assert not list((temp_dir / "maps" / "amap").glob("*.png"))


def test_layout_map_widgets_finds_two_default_drone_maps(temp_dir):
    from gpstitch.services.map_cache import MapCacheService

    service = MapCacheService(cache_dir=temp_dir / "maps")

    widgets = service.get_layout_map_widgets("dji-drone-1920x1080")

    assert [w.name for w in widgets] == ["moving_map", "journey_map"]
    assert widgets[0].x == 1644
    assert widgets[1].y == 376
