"""Pydantic request/response models for GPStitch API."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from gpstitch.constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_GPS_DOP_MAX,
    DEFAULT_GPS_SPEED_MAX,
    DEFAULT_UNITS_ALTITUDE,
    DEFAULT_UNITS_DISTANCE,
    DEFAULT_UNITS_SPEED,
    DEFAULT_UNITS_TEMPERATURE,
)

LanguageCode = Literal["zh-CN", "en"]


class FileRole(str, Enum):
    """Role of a file in the session."""

    PRIMARY = "primary"  # Main video or GPX/FIT for overlay-only mode
    SECONDARY = "secondary"  # GPX/FIT to merge with video


class VideoMetadata(BaseModel):
    """Metadata extracted from a video file."""

    width: int
    height: int
    duration_seconds: float
    frame_count: int
    frame_rate: float
    has_gps: bool
    has_dji_meta: bool = False
    dji_meta_point_count: int | None = None


class GpxFitMetadata(BaseModel):
    """Metadata extracted from a GPX or FIT file."""

    gps_point_count: int
    duration_seconds: float | None = None


# Type alias for GPS quality scores
GPSQualityScore = Literal["excellent", "good", "ok", "poor", "no_signal"]


class GPSQualityReport(BaseModel):
    """GPS signal quality analysis report."""

    # General statistics
    total_points: int = Field(description="Total number of GPS data points")
    locked_points: int = Field(description="Number of points with GPS lock")
    lock_rate: float = Field(description="Percentage of points with GPS lock (0-100)")

    # DOP (Dilution of Precision) statistics
    dop_min: float | None = Field(default=None, description="Minimum DOP value")
    dop_max: float | None = Field(default=None, description="Maximum DOP value")
    dop_mean: float | None = Field(default=None, description="Mean DOP value")
    dop_median: float | None = Field(default=None, description="Median DOP value")

    # Quality distribution (point counts by DOP range)
    excellent_count: int = Field(default=0, description="Points with DOP < 2")
    good_count: int = Field(default=0, description="Points with DOP 2-5")
    moderate_count: int = Field(default=0, description="Points with DOP 5-10")
    poor_count: int = Field(default=0, description="Points with DOP > 10")

    # Overall assessment
    quality_score: GPSQualityScore = Field(description="Overall quality rating")
    usable_percentage: float = Field(description="Percentage of points with acceptable quality (DOP < 10)")

    # User guidance
    warnings: list[str] = Field(default_factory=list, description="Warning messages for the user")


class FileInfo(BaseModel):
    """Information about a file in the session."""

    filename: str
    file_path: str
    file_type: str  # "video", "gpx", "fit", "srt"
    role: FileRole
    video_metadata: VideoMetadata | None = None
    gpx_fit_metadata: GpxFitMetadata | None = None
    gps_quality: GPSQualityReport | None = None


class GpxFitOptions(BaseModel):
    """Options for GPX/FIT processing."""

    merge_mode: str = "OVERWRITE"  # "EXTEND" or "OVERWRITE"
    video_time_alignment: Literal["auto", "gpx-timestamps", "manual"] = "auto"
    time_offset_seconds: int = 0


class UploadResponse(BaseModel):
    """Response from file upload endpoint."""

    session_id: str
    files: list[FileInfo]  # All files in session with roles


class LayoutInfo(BaseModel):
    """Information about an available layout."""

    name: str
    display_name: str
    width: int
    height: int
    requires_cairo: bool = False


class LayoutsResponse(BaseModel):
    """Response from layouts endpoint."""

    layouts: list[LayoutInfo]
    cairo_available: bool = False


class UnitOption(BaseModel):
    """A single unit option."""

    value: str
    label: str


class UnitCategory(BaseModel):
    """A category of units with available options."""

    name: str
    label: str
    options: list[UnitOption]
    default: str


class UnitOptionsResponse(BaseModel):
    """Response from unit options endpoint."""

    categories: list[UnitCategory]


class MapStyleOption(BaseModel):
    """A single map style option."""

    name: str
    display_name: str
    requires_api_key: bool = False
    provider: str = "gopro-overlay"
    requires_security_js_code: bool = False
    configured: bool | None = None
    validated: bool | None = None
    key_fingerprint: str | None = None


class MapStylesResponse(BaseModel):
    """Response from map styles endpoint."""

    styles: list[MapStyleOption]


class FFmpegProfileOption(BaseModel):
    """A single FFmpeg profile option."""

    name: str
    display_name: str
    description: str
    is_builtin: bool = True


class FFmpegProfilesResponse(BaseModel):
    """Response from FFmpeg profiles endpoint."""

    profiles: list[FFmpegProfileOption]


class PreviewRequest(BaseModel):
    """Request for generating a preview image."""

    session_id: str
    layout: str = "default-1920x1080"
    frame_time_ms: int = Field(default=0, ge=0)
    units_speed: str = DEFAULT_UNITS_SPEED
    units_altitude: str = DEFAULT_UNITS_ALTITUDE
    units_distance: str = DEFAULT_UNITS_DISTANCE
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE
    map_style: str | None = None
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX
    video_time_alignment: Literal["auto", "gpx-timestamps", "manual"] = "auto"
    time_offset_seconds: int = 0
    language: LanguageCode = DEFAULT_LANGUAGE


class PreviewResponse(BaseModel):
    """Response from preview generation endpoint."""

    image_base64: str
    width: int
    height: int
    frame_time_ms: int


class CommandRequest(BaseModel):
    """Request for generating a CLI command."""

    session_id: str
    layout: str = "default-1920x1080"
    layout_xml_path: str | None = None  # Path to custom template XML
    output_filename: str | None = None  # Auto-generated from input if not specified
    units_speed: str = DEFAULT_UNITS_SPEED
    units_altitude: str = DEFAULT_UNITS_ALTITUDE
    units_distance: str = DEFAULT_UNITS_DISTANCE
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE
    map_style: str | None = None
    gpx_fit_options: GpxFitOptions | None = None  # GPX/FIT merge options
    ffmpeg_profile: str | None = None  # FFmpeg encoding profile
    language: LanguageCode = DEFAULT_LANGUAGE


class CommandResponse(BaseModel):
    """Response from command generation endpoint."""

    command: str
    input_file: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None


class LocalFileRequest(BaseModel):
    """Request for using a local file path."""

    file_path: str
    session_id: str | None = None


class SecondaryFileRequest(BaseModel):
    """Request for adding a secondary GPX/FIT file."""

    session_id: str
    file_path: str  # For local mode


class ConfigResponse(BaseModel):
    """Response with app configuration."""

    local_mode: bool
    max_upload_size_bytes: int
    allowed_extensions: list[str]
    default_language: LanguageCode = DEFAULT_LANGUAGE


class AMapSettingsUpdateRequest(BaseModel):
    """Request to save AMap JS API credentials."""

    key: str = Field(min_length=1)
    security_js_code: str = Field(min_length=1)


class AMapValidationRequest(BaseModel):
    """Request to record an AMap validation result."""

    success: bool
    error: str | None = None


class AMapSettingsResponse(BaseModel):
    """Redacted AMap settings metadata."""

    configured: bool = False
    validated: bool = False
    key_fingerprint: str | None = None
    last_validated_at: str | None = None
    last_error: str | None = None
    validation_generation: int = 0


class AMapRuntimeConfigResponse(BaseModel):
    """AMap runtime config for the local browser renderer."""

    configured: bool
    validated: bool = False
    key: str | None = None
    security_js_code: str | None = None
    key_fingerprint: str | None = None


class AMapRoutePoint(BaseModel):
    """A route point for browser-side AMap rendering."""

    lat: float
    lon: float


class AMapMapWidget(BaseModel):
    """Preview map widget rectangle that can be replaced by AMap."""

    name: str
    type: str
    x: int
    y: int
    width: int
    height: int
    zoom: int = 16
    corner_radius: int = 0
    opacity: float = 0.7
    rotate: bool = True
    line_fill: str = "#1f8fff"
    line_width: int = 5


class AMapRenderContextRequest(BaseModel):
    """Request for browser-side AMap overlay context."""

    session_id: str
    layout: str = "default-1920x1080"
    frame_time_ms: int = Field(default=0, ge=0)
    language: LanguageCode = DEFAULT_LANGUAGE


class AMapRenderContextResponse(BaseModel):
    """Route and widget geometry for browser-side AMap rendering."""

    success: bool
    provider: str = "amap"
    canvas_width: int = 1920
    canvas_height: int = 1080
    route_points: list[AMapRoutePoint] = Field(default_factory=list)
    map_widgets: list[AMapMapWidget] = Field(default_factory=list)
    cache_key: str | None = None
    message: str | None = None


class AMapCacheClearResponse(BaseModel):
    """Result of clearing AMap-specific cached state."""

    success: bool
    removed: bool = False
    message: str


class LocalFileDialogRequest(BaseModel):
    """Request to open a local file picker."""

    file_kind: Literal["video", "gps", "any-supported"] = "any-supported"
    title: str | None = None
    initial_dir: str | None = None
    language: LanguageCode = DEFAULT_LANGUAGE


class LocalFileDialogResponse(BaseModel):
    """Response from a local file picker."""

    selected: bool
    file_path: str | None = None
    message: str | None = None


class LocalDirectoryDialogRequest(BaseModel):
    """Request to open a local directory picker."""

    title: str | None = None
    initial_dir: str | None = None
    language: LanguageCode = DEFAULT_LANGUAGE


class LocalDirectoryDialogResponse(BaseModel):
    """Response from a local directory picker."""

    selected: bool
    directory_path: str | None = None
    message: str | None = None


class BatchDirectoryListRequest(BaseModel):
    """Request to list supported batch-render files from a local directory."""

    directory_path: str
    recursive: bool = False
    language: LanguageCode = DEFAULT_LANGUAGE


class BatchDirectoryFile(BaseModel):
    """A discovered video and optional matching telemetry file."""

    video_path: str
    gpx_path: str | None = None
    telemetry_type: str | None = None


class BatchDirectoryListResponse(BaseModel):
    """Supported files discovered in a local directory."""

    directory_path: str
    files: list[BatchDirectoryFile]
    total_videos: int
    message: str | None = None


class MapCacheWarmupRequest(BaseModel):
    """Request to warm map tiles for a loaded session route."""

    session_id: str
    map_style: str = "osm"
    layout: str | None = None
    language: LanguageCode = DEFAULT_LANGUAGE


class MapCacheWarmupResponse(BaseModel):
    """Result of map cache warmup."""

    success: bool
    cache_dir: str
    route_points: int = 0
    rendered_maps: int = 0
    capped: bool = False
    provider: str = "gopro-overlay"
    cache_key: str | None = None
    message: str


# Template management models
class TemplateInfo(BaseModel):
    """Information about a saved template."""

    name: str
    file_path: str
    created_at: str | None = None
    modified_at: str | None = None
    canvas_width: int = 1920
    canvas_height: int = 1080
    description: str | None = None


class SaveTemplateRequest(BaseModel):
    """Request to save a custom template."""

    name: str
    layout: dict  # EditorLayout as dict from frontend
    description: str | None = None


class SaveTemplateResponse(BaseModel):
    """Response from saving template."""

    name: str
    file_path: str
    success: bool = True


class TemplateListResponse(BaseModel):
    """Response with list of templates."""

    templates: list[TemplateInfo]


class RenameTemplateRequest(BaseModel):
    """Request to rename a template."""

    new_name: str
