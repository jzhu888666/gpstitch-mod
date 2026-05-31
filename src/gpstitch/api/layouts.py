"""Layouts API endpoint."""

from fastapi import APIRouter, Query

from gpstitch.constants import is_pycairo_available
from gpstitch.models.schemas import LayoutInfo, LayoutsResponse
from gpstitch.services.localization import localize_layout_name, normalize_language
from gpstitch.services.renderer import get_available_layouts

router = APIRouter()


@router.get("/layouts", response_model=LayoutsResponse)
async def get_layouts(language: str = Query("zh-CN")) -> LayoutsResponse:
    """Get list of available dashboard layouts."""
    lang = normalize_language(language)
    layouts = get_available_layouts()
    return LayoutsResponse(
        layouts=[
            LayoutInfo(
                name=layout.name,
                display_name=localize_layout_name(layout.name, layout.display_name, lang),
                width=layout.width,
                height=layout.height,
                requires_cairo=layout.requires_cairo,
            )
            for layout in layouts
        ],
        cairo_available=is_pycairo_available(),
    )
