"""Map cache API endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException

from gpstitch.models.schemas import MapCacheWarmupRequest, MapCacheWarmupResponse
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
