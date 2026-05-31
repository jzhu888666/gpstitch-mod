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
