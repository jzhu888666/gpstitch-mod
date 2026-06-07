"""Command generation API endpoint."""

from fastapi import APIRouter, HTTPException

from gpstitch.models.schemas import CommandRequest, CommandResponse
from gpstitch.services.amap_settings import amap_settings_service, backend_map_style, is_amap_style
from gpstitch.services.file_manager import file_manager
from gpstitch.services.renderer import generate_cli_command

router = APIRouter()


@router.post("/command", response_model=CommandResponse)
async def generate_command(request: CommandRequest) -> CommandResponse:
    """Generate the CLI command for full video processing."""
    # Validate session exists
    if not file_manager.session_exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Get the primary file path for response
    primary_file = file_manager.get_primary_file(request.session_id)
    if primary_file is None:
        raise HTTPException(status_code=404, detail="No primary file in session")

    # Extract GPX/FIT options
    gpx_merge_mode = "OVERWRITE"
    video_time_alignment = None
    time_offset_seconds = 0
    if request.gpx_fit_options:
        gpx_merge_mode = request.gpx_fit_options.merge_mode
        video_time_alignment = request.gpx_fit_options.video_time_alignment
        time_offset_seconds = request.gpx_fit_options.time_offset_seconds

    # Generate the command (temp_files are not needed for display-only use)
    amap_render = is_amap_style(request.map_style)
    if amap_render:
        amap_runtime = amap_settings_service.get_runtime_config()
        if not amap_runtime.configured or not amap_runtime.validated:
            raise HTTPException(
                status_code=400,
                detail="AMap credentials must be configured and validated before command generation.",
            )
    command, _temp_files = generate_cli_command(
        session_id=request.session_id,
        output_file=request.output_filename,
        layout=request.layout,
        layout_xml_path=request.layout_xml_path,
        units_speed=request.units_speed,
        units_altitude=request.units_altitude,
        units_distance=request.units_distance,
        units_temperature=request.units_temperature,
        map_style=None if amap_render else backend_map_style(request.map_style),
        gpx_merge_mode=gpx_merge_mode,
        video_time_alignment=video_time_alignment,
        time_offset_seconds=time_offset_seconds,
        ffmpeg_profile=request.ffmpeg_profile,
        language=request.language,
        amap_render=amap_render,
        amap_map_style=request.map_style if amap_render else None,
    )

    return CommandResponse(
        command=command,
        input_file=primary_file.file_path,
    )
