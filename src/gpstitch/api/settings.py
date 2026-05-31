"""Application settings API endpoints."""

from fastapi import APIRouter, HTTPException

from gpstitch.models.schemas import (
    AMapRuntimeConfigResponse,
    AMapSettingsResponse,
    AMapSettingsUpdateRequest,
    AMapValidationRequest,
)
from gpstitch.services.amap_settings import amap_settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/amap", response_model=AMapSettingsResponse)
async def get_amap_settings() -> AMapSettingsResponse:
    """Return redacted AMap settings metadata."""
    return amap_settings_service.get_settings()


@router.put("/amap", response_model=AMapSettingsResponse)
async def save_amap_settings(request: AMapSettingsUpdateRequest) -> AMapSettingsResponse:
    """Save local AMap JSAPI credentials."""
    try:
        return amap_settings_service.save_credentials(request.key, request.security_js_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/amap", response_model=AMapSettingsResponse)
async def clear_amap_settings() -> AMapSettingsResponse:
    """Clear local AMap JSAPI credentials."""
    return amap_settings_service.clear()


@router.post("/amap/validate", response_model=AMapSettingsResponse)
async def record_amap_validation(request: AMapValidationRequest) -> AMapSettingsResponse:
    """Record the browser-side AMap validation result."""
    try:
        return amap_settings_service.record_validation(request.success, request.error)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/amap/runtime-config", response_model=AMapRuntimeConfigResponse)
async def get_amap_runtime_config() -> AMapRuntimeConfigResponse:
    """Return runtime credentials for the local browser AMap renderer."""
    return amap_settings_service.get_runtime_config()
