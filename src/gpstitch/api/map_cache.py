"""Map cache API endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException

from gpstitch.models.schemas import (
    AMapCacheClearResponse,
    AMapRenderContextRequest,
    AMapRenderContextResponse,
    MapCacheWarmupRequest,
    MapCacheWarmupResponse,
)
from gpstitch.services.file_manager import file_manager
from gpstitch.services.map_cache import map_cache_service

router = APIRouter(prefix="/api/map-cache", tags=["map-cache"])


@router.post("/warmup", response_model=MapCacheWarmupResponse)
async def warm_map_cache(request: MapCacheWarmupRequest) -> MapCacheWarmupResponse:
    """Warm project-local map cache for the active session."""
    if not file_manager.session_exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return await asyncio.to_thread(
        map_cache_service.warm_session_cache,
        session_id=request.session_id,
        map_style=request.map_style,
        layout=request.layout,
        language=request.language,
    )


@router.post("/amap-context", response_model=AMapRenderContextResponse)
async def get_amap_context(request: AMapRenderContextRequest) -> AMapRenderContextResponse:
    """Return route and widget geometry for browser-side AMap overlays."""
    if not file_manager.session_exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return await asyncio.to_thread(
        map_cache_service.build_amap_render_context,
        session_id=request.session_id,
        layout=request.layout,
        frame_time_ms=request.frame_time_ms,
        language=request.language,
        map_style=request.map_style,
    )


@router.delete("/amap", response_model=AMapCacheClearResponse)
async def clear_amap_cache() -> AMapCacheClearResponse:
    """Clear AMap-specific GPStitch cache entries."""
    removed = await asyncio.to_thread(map_cache_service.clear_amap_cache)
    return AMapCacheClearResponse(
        success=True,
        removed=removed,
        message="AMap cache cleared" if removed else "AMap cache was already empty",
    )
