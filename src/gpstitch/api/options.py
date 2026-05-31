"""Options API endpoints for units, map styles, and FFmpeg profiles."""

from fastapi import APIRouter, Query

from gpstitch.models.schemas import (
    FFmpegProfileOption,
    FFmpegProfilesResponse,
    MapStyleOption,
    MapStylesResponse,
    UnitCategory,
    UnitOption,
    UnitOptionsResponse,
)
from gpstitch.services.localization import (
    localize_ffmpeg_profile,
    localize_map_style_name,
    localize_unit_options,
    normalize_language,
)
from gpstitch.services.amap_settings import AMAP_PROVIDER, amap_settings_service
from gpstitch.services.renderer import (
    get_available_ffmpeg_profiles,
    get_available_map_styles,
    get_available_units,
)

router = APIRouter()


@router.get("/options/units", response_model=UnitOptionsResponse)
async def get_unit_options(language: str = Query("zh-CN")) -> UnitOptionsResponse:
    """Get available unit options for speed, altitude, distance, and temperature."""
    units = localize_unit_options(get_available_units(), normalize_language(language))

    categories = []
    for name, category_data in units.items():
        options = [UnitOption(value=opt["value"], label=opt["label"]) for opt in category_data["options"]]
        categories.append(
            UnitCategory(
                name=name,
                label=category_data["label"],
                options=options,
                default=category_data["default"],
            )
        )

    return UnitOptionsResponse(categories=categories)


@router.get("/options/map-styles", response_model=MapStylesResponse)
async def get_map_styles(language: str = Query("zh-CN")) -> MapStylesResponse:
    """Get available map styles."""
    lang = normalize_language(language)
    styles = get_available_map_styles()
    amap_settings = amap_settings_service.get_settings()
    return MapStylesResponse(
        styles=[
            MapStyleOption(
                name=s["name"],
                display_name=localize_map_style_name(s["name"], s["display_name"], lang),
                requires_api_key=s.get("requires_api_key", False),
                provider=s.get("provider", "gopro-overlay"),
                requires_security_js_code=s.get("requires_security_js_code", False),
                configured=amap_settings.configured if s.get("provider") == AMAP_PROVIDER else None,
                validated=amap_settings.validated if s.get("provider") == AMAP_PROVIDER else None,
                key_fingerprint=amap_settings.key_fingerprint if s.get("provider") == AMAP_PROVIDER else None,
            )
            for s in styles
        ]
    )


@router.get("/options/ffmpeg-profiles", response_model=FFmpegProfilesResponse)
async def get_ffmpeg_profiles(language: str = Query("zh-CN")) -> FFmpegProfilesResponse:
    """Get available FFmpeg encoding profiles."""
    lang = normalize_language(language)
    profiles = get_available_ffmpeg_profiles()
    localized_profiles = []
    for profile in profiles:
        display_name, description = localize_ffmpeg_profile(
            profile["name"],
            profile["display_name"],
            profile["description"],
            lang,
        )
        localized_profiles.append({**profile, "display_name": display_name, "description": description})
    return FFmpegProfilesResponse(
        profiles=[
            FFmpegProfileOption(
                name=p["name"],
                display_name=p["display_name"],
                description=p["description"],
                is_builtin=p.get("is_builtin", True),
            )
            for p in localized_profiles
        ]
    )
