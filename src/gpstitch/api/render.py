"""Render job API endpoints."""

import asyncio
import contextlib
import datetime
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from gpstitch.constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_GPS_DOP_MAX,
    DEFAULT_GPS_SPEED_MAX,
    DEFAULT_GPX_MERGE_MODE,
    DEFAULT_UNITS_ALTITUDE,
    DEFAULT_UNITS_DISTANCE,
    DEFAULT_UNITS_SPEED,
    DEFAULT_UNITS_TEMPERATURE,
)
from gpstitch.models.job import Job, JobStatus, RenderJobConfig, migrate_video_time_alignment
from gpstitch.models.schemas import FileRole
from gpstitch.services.file_manager import file_manager
from gpstitch.services.job_manager import job_manager
from gpstitch.services.metadata import extract_gpx_fit_metadata, extract_video_metadata
from gpstitch.services.power import power_service
from gpstitch.services.render_service import render_service
from gpstitch.services.runtime_settings import runtime_settings_service

router = APIRouter()
logger = logging.getLogger(__name__)


# Request/Response models
class RenderJobRequest(BaseModel):
    """Request to start a render job."""

    session_id: str
    layout: str = "default-1920x1080"
    layout_xml_path: str | None = None
    output_file: str | None = None  # Auto-generated if not provided
    units_speed: str = DEFAULT_UNITS_SPEED
    units_altitude: str = DEFAULT_UNITS_ALTITUDE
    units_distance: str = DEFAULT_UNITS_DISTANCE
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE
    map_style: str | None = None
    gpx_merge_mode: str = DEFAULT_GPX_MERGE_MODE
    video_time_alignment: str = "auto"
    time_offset_seconds: int = 0
    ffmpeg_profile: str | None = None  # FFmpeg encoding profile (e.g., "mac", "nvgpu")
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX
    language: str = DEFAULT_LANGUAGE

    @field_validator("video_time_alignment", mode="before")
    @classmethod
    def _migrate_alignment(cls, v: str | None) -> str:
        return migrate_video_time_alignment(v)


class RenderJobResponse(BaseModel):
    """Response from starting a render job."""

    job_id: str
    status: str
    output_file: str


class JobProgressResponse(BaseModel):
    """Job progress information."""

    percent: float = Field(ge=0, le=100)
    current_frame: int | None = None
    total_frames: int | None = None
    fps: float | None = None
    eta_seconds: float | None = None


class JobStatusResponse(BaseModel):
    """Response with job status."""

    job_id: str
    status: str
    progress: JobProgressResponse
    output_file: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3


class RenderJobListItem(BaseModel):
    """Render job summary for the task manager."""

    job_id: str
    batch_id: str | None = None
    status: str
    video_name: str
    source_file: str | None = None
    output_file: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: JobProgressResponse
    error: str | None = None
    can_cancel: bool = False
    retry_count: int = 0
    max_retries: int = 3


class RenderJobListResponse(BaseModel):
    """Recent render jobs."""

    jobs: list[RenderJobListItem]
    total: int
    active_job_id: str | None = None
    active_job_ids: list[str] = Field(default_factory=list)
    render_concurrency: int = 1
    shutdown_after_all_tasks: bool = False
    shutdown_supported: bool = False
    queue_mode: str = "concurrent"


class RenderJobClearRequest(BaseModel):
    """Request to remove finished render jobs from the task manager."""

    statuses: list[JobStatus] = Field(
        default_factory=lambda: [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    )


class RenderJobClearResponse(BaseModel):
    """Response from finished-job cleanup."""

    removed: int
    statuses: list[str]


class RenderJobBulkActionRequest(BaseModel):
    """Request to apply an action to selected render jobs."""

    job_ids: list[str] = Field(min_length=1, max_length=500)


class RenderJobBulkActionResult(BaseModel):
    """Result for one selected render job."""

    job_id: str
    status: str
    detail: str | None = None


class RenderJobBulkActionResponse(BaseModel):
    """Response from a selected-job bulk action."""

    requested: int
    affected: int
    skipped: int
    jobs: list[RenderJobBulkActionResult]


class RenderConcurrencyRequest(BaseModel):
    """Request to update render concurrency."""

    concurrency: int = Field(ge=1, le=3)


class RenderConcurrencyResponse(BaseModel):
    """Current render concurrency settings."""

    concurrency: int
    min_concurrency: int = 1
    max_concurrency: int = 3


class TaskShutdownSettingsRequest(BaseModel):
    """Request to update the task-manager shutdown setting."""

    enabled: bool


class TaskShutdownSettingsResponse(BaseModel):
    """Current task-manager shutdown setting."""

    enabled: bool
    supported: bool


class JobLogsResponse(BaseModel):
    """Response with job logs."""

    job_id: str
    log_lines: list[str]
    total_lines: int


class CurrentJobResponse(BaseModel):
    """Response with current job info."""

    job_id: str | None = None
    status: str | None = None
    progress: JobProgressResponse | None = None


class FileCheckRequest(BaseModel):
    """Request to check if output files exist."""

    output_files: list[str] = Field(min_length=1, max_length=100)


class FileCheckResponse(BaseModel):
    """Response with list of existing files."""

    existing_files: list[str]
    total_checked: int


TERMINAL_CLEAR_STATUS_ORDER = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
TERMINAL_CLEAR_STATUSES = set(TERMINAL_CLEAR_STATUS_ORDER)


def _job_progress_response(job: Job) -> JobProgressResponse:
    return JobProgressResponse(
        percent=job.progress.percent,
        current_frame=job.progress.current_frame,
        total_frames=job.progress.total_frames,
        fps=job.progress.fps,
        eta_seconds=job.progress.eta_seconds,
    )


def _job_video_name_and_source(job: Job) -> tuple[str, str | None]:
    primary = None
    with contextlib.suppress(Exception):
        primary = file_manager.get_primary_file(job.config.session_id)

    if primary:
        return primary.filename, primary.file_path

    output_path = Path(job.config.output_file)
    fallback_name = output_path.name or job.config.session_id
    return fallback_name, None


def _job_list_item(job: Job) -> RenderJobListItem:
    video_name, source_file = _job_video_name_and_source(job)
    return RenderJobListItem(
        job_id=job.id,
        batch_id=job.batch_id,
        status=job.status.value,
        video_name=video_name,
        source_file=source_file,
        output_file=job.config.output_file,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        progress=_job_progress_response(job),
        error=job.error,
        can_cancel=job.status in (JobStatus.PENDING, JobStatus.RUNNING),
        retry_count=job.retry_count,
        max_retries=job.max_retries,
    )


def _unique_job_ids(job_ids: list[str]) -> list[str]:
    """Return non-empty job ids once, preserving selection order."""
    return list(dict.fromkeys(job_id.strip() for job_id in job_ids if job_id and job_id.strip()))


async def _cancel_render_job(job: Job) -> tuple[bool, str]:
    """Cancel a queued or running render job and return action detail."""
    if job.status == JobStatus.PENDING:
        if render_service.is_job_active(job.id):
            success = await render_service.cancel_render(job.id)
            return success, "cancelled" if success else "Failed to cancel active queued job"
        await job_manager.update_job_status(job.id, JobStatus.CANCELLED)
        return True, "cancelled"

    if job.is_terminal():
        return False, "Job is already finished"

    if not job.is_running():
        return False, "Job cannot be cancelled"

    success = await render_service.cancel_render(job.id)
    return success, "cancelled" if success else "Failed to cancel running job"


# --- Pre-check for batch render (overwrite + GPS quality) ---


class PreCheckFileInput(BaseModel):
    """Input file for pre-check."""

    video_path: str
    gpx_path: str | None = None


class PreCheckRequest(BaseModel):
    """Request to pre-check files before batch render."""

    files: list[PreCheckFileInput] = Field(min_length=1, max_length=1000)
    shared_gpx_path: str | None = None
    ffmpeg_profile: str | None = None


class OverwriteConflict(BaseModel):
    """File with overwrite conflict."""

    video_path: str
    output_path: str


class GPSFileInfo(BaseModel):
    """GPS quality info for a file."""

    video_path: str
    quality_score: str  # excellent, good, ok, poor, no_signal, skipped, not_found
    usable_percentage: float | None = None
    dop_mean: float | None = None
    has_external_gps: bool = False  # True if GPX/FIT provided


class PreCheckResponse(BaseModel):
    """Response from pre-check with overwrite and GPS issues."""

    total_files: int
    overwrite_conflicts: list[OverwriteConflict]
    gps_files: list[GPSFileInfo]  # All files with GPS info
    gps_issues_count: int  # Count of poor/no_signal files


@router.post("/render/pre-check", response_model=PreCheckResponse)
async def pre_check_batch_files(request: PreCheckRequest) -> PreCheckResponse:
    """Pre-check batch files for overwrite conflicts and GPS quality issues.

    Returns info for all files so the frontend can show a complete table.
    """
    from gpstitch.services.gps_analyzer import analyze_gps_quality

    overwrite_conflicts: list[OverwriteConflict] = []
    gps_files: list[GPSFileInfo] = []
    gps_issues_count = 0

    for file_input in request.files:
        video_path = Path(file_input.video_path).expanduser().resolve()

        # Handle non-existent files
        if not video_path.exists():
            gps_files.append(
                GPSFileInfo(
                    video_path=str(video_path),
                    quality_score="not_found",
                )
            )
            continue

        # Check overwrite conflict
        from gpstitch.services.renderer import get_output_extension_for_profile

        ext = get_output_extension_for_profile(request.ffmpeg_profile)
        output_path = video_path.parent / f"{video_path.stem}_overlay{ext}"
        if output_path.exists():
            overwrite_conflicts.append(
                OverwriteConflict(
                    video_path=str(video_path),
                    output_path=str(output_path),
                )
            )

        # Analyze GPS quality
        suffix = video_path.suffix.lower()
        if suffix in [".mp4", ".mov", ".avi"]:
            # If external GPX/FIT provided (per-file or shared), mark as skipped
            effective_gpx = file_input.gpx_path or request.shared_gpx_path
            gpx_exists = False
            if effective_gpx:
                with contextlib.suppress(ValueError, OSError):
                    gpx_exists = Path(effective_gpx).expanduser().resolve().exists()
            if gpx_exists:
                gps_files.append(
                    GPSFileInfo(
                        video_path=str(video_path),
                        quality_score="skipped",
                        has_external_gps=True,
                    )
                )
            else:
                try:
                    report = analyze_gps_quality(video_path)
                    if report:
                        gps_files.append(
                            GPSFileInfo(
                                video_path=str(video_path),
                                quality_score=report.quality_score,
                                usable_percentage=report.usable_percentage,
                                dop_mean=report.dop_mean,
                            )
                        )
                        if report.quality_score in ["poor", "no_signal"]:
                            gps_issues_count += 1
                    else:
                        gps_files.append(
                            GPSFileInfo(
                                video_path=str(video_path),
                                quality_score="unknown",
                            )
                        )
                except Exception as e:
                    logger.warning(f"Failed to analyze GPS for {video_path}: {e}")
                    gps_files.append(
                        GPSFileInfo(
                            video_path=str(video_path),
                            quality_score="error",
                        )
                    )
        else:
            # Non-video files (GPX, FIT) - skip GPS analysis
            gps_files.append(
                GPSFileInfo(
                    video_path=str(video_path),
                    quality_score="skipped",
                )
            )

    return PreCheckResponse(
        total_files=len(request.files),
        overwrite_conflicts=overwrite_conflicts,
        gps_files=gps_files,
        gps_issues_count=gps_issues_count,
    )


@router.post("/render/check-files", response_model=FileCheckResponse)
async def check_output_files(request: FileCheckRequest) -> FileCheckResponse:
    """Check which output files already exist on filesystem."""
    existing = []
    for file_path in request.output_files:
        try:
            # Resolve and sanitize path
            resolved_path = Path(file_path).expanduser().resolve()
            if resolved_path.exists() and resolved_path.is_file():
                existing.append(str(resolved_path))
        except (ValueError, OSError) as e:
            logger.warning(f"Invalid path in check-files: {file_path}, error: {e}")
            continue

    return FileCheckResponse(existing_files=existing, total_checked=len(request.output_files))


@router.post("/render/start", response_model=RenderJobResponse)
async def start_render(request: RenderJobRequest) -> RenderJobResponse:
    """Start a new render job."""

    # Validate session
    if not file_manager.session_exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Get primary file info
    primary = file_manager.get_primary_file(request.session_id)
    if not primary:
        raise HTTPException(status_code=404, detail="No primary file in session")

    # Auto-generate output filename if not specified
    output_file = request.output_file
    if not output_file:
        from gpstitch.services.renderer import get_output_extension_for_profile

        primary_dir = os.path.dirname(primary.file_path)
        primary_name = os.path.splitext(os.path.basename(primary.file_path))[0]
        ext = get_output_extension_for_profile(request.ffmpeg_profile)
        output_file = os.path.join(primary_dir, f"{primary_name}_overlay{ext}")

    # Create job config
    config = RenderJobConfig(
        session_id=request.session_id,
        layout=request.layout,
        layout_xml_path=request.layout_xml_path,
        output_file=output_file,
        units_speed=request.units_speed,
        units_altitude=request.units_altitude,
        units_distance=request.units_distance,
        units_temperature=request.units_temperature,
        map_style=request.map_style,
        gpx_merge_mode=request.gpx_merge_mode,
        video_time_alignment=request.video_time_alignment,
        time_offset_seconds=request.time_offset_seconds,
        ffmpeg_profile=request.ffmpeg_profile,
        gps_dop_max=request.gps_dop_max,
        gps_speed_max=request.gps_speed_max,
        language=request.language,
    )

    # Create job
    job = await job_manager.create_job(config)

    # Start when a render slot is available. This only schedules render
    # workers; it does not wait for the subprocesses to finish.
    await render_service.kick_queue()

    logger.info(f"Queued render job {job.id} for session {request.session_id}")

    return RenderJobResponse(
        job_id=job.id,
        status=job.status.value,
        output_file=output_file,
    )


@router.get("/render/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get status of a render job."""

    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        progress=JobProgressResponse(
            percent=job.progress.percent,
            current_frame=job.progress.current_frame,
            total_frames=job.progress.total_frames,
            fps=job.progress.fps,
            eta_seconds=job.progress.eta_seconds,
        ),
        output_file=job.config.output_file,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error=job.error,
        retry_count=job.retry_count,
        max_retries=job.max_retries,
    )


@router.get("/render/jobs", response_model=RenderJobListResponse)
async def list_render_jobs(limit: int = Query(default=100, ge=1, le=500)) -> RenderJobListResponse:
    """List recent render jobs for the task manager."""

    jobs = await job_manager.list_jobs(limit=limit)
    current = await job_manager.get_current_job()
    running_jobs = await job_manager.get_running_jobs()
    return RenderJobListResponse(
        jobs=[_job_list_item(job) for job in jobs],
        total=len(jobs),
        active_job_id=current.id if current else None,
        active_job_ids=[job.id for job in running_jobs],
        render_concurrency=render_service.concurrency,
        shutdown_after_all_tasks=runtime_settings_service.get_shutdown_after_all_tasks(False),
        shutdown_supported=power_service.supports_shutdown(),
    )


@router.post("/render/jobs/clear", response_model=RenderJobClearResponse)
async def clear_render_jobs(request: RenderJobClearRequest) -> RenderJobClearResponse:
    """Remove completed, failed, and cancelled jobs from the task manager."""

    requested = set(request.statuses)
    if not requested:
        raise HTTPException(status_code=400, detail="At least one status is required")

    invalid = requested - TERMINAL_CLEAR_STATUSES
    if invalid:
        allowed = ", ".join(status.value for status in TERMINAL_CLEAR_STATUS_ORDER)
        raise HTTPException(status_code=400, detail=f"Only finished jobs can be removed: {allowed}")

    ordered_statuses = [status for status in TERMINAL_CLEAR_STATUS_ORDER if status in requested]
    removed = await job_manager.remove_jobs_by_status(set(ordered_statuses))
    return RenderJobClearResponse(
        removed=removed,
        statuses=[status.value for status in ordered_statuses],
    )


@router.post("/render/jobs/retry", response_model=RenderJobBulkActionResponse)
async def retry_render_jobs(request: RenderJobBulkActionRequest) -> RenderJobBulkActionResponse:
    """Retry selected failed render jobs."""

    job_ids = _unique_job_ids(request.job_ids)
    if not job_ids:
        raise HTTPException(status_code=400, detail="At least one job id is required")

    results: list[RenderJobBulkActionResult] = []
    affected = 0
    for job_id in job_ids:
        job = await job_manager.get_job(job_id)
        if not job:
            results.append(RenderJobBulkActionResult(job_id=job_id, status="skipped", detail="Job not found"))
            continue

        if job.status != JobStatus.FAILED:
            results.append(
                RenderJobBulkActionResult(job_id=job_id, status="skipped", detail="Only failed jobs can be retried")
            )
            continue

        if await job_manager.retry_failed_job(job_id):
            affected += 1
            results.append(RenderJobBulkActionResult(job_id=job_id, status="retried"))
        else:
            results.append(RenderJobBulkActionResult(job_id=job_id, status="skipped", detail="Retry failed"))

    if affected:
        await render_service.kick_queue()

    return RenderJobBulkActionResponse(
        requested=len(job_ids),
        affected=affected,
        skipped=len(job_ids) - affected,
        jobs=results,
    )


@router.post("/render/jobs/cancel", response_model=RenderJobBulkActionResponse)
async def cancel_render_jobs(request: RenderJobBulkActionRequest) -> RenderJobBulkActionResponse:
    """Cancel selected queued or running render jobs."""

    job_ids = _unique_job_ids(request.job_ids)
    if not job_ids:
        raise HTTPException(status_code=400, detail="At least one job id is required")

    results: list[RenderJobBulkActionResult] = []
    affected = 0
    for job_id in job_ids:
        job = await job_manager.get_job(job_id)
        if not job:
            results.append(RenderJobBulkActionResult(job_id=job_id, status="skipped", detail="Job not found"))
            continue

        success, detail = await _cancel_render_job(job)
        if success:
            affected += 1
            results.append(RenderJobBulkActionResult(job_id=job_id, status="cancelled"))
        else:
            results.append(RenderJobBulkActionResult(job_id=job_id, status="skipped", detail=detail))

    if affected:
        await render_service.kick_queue()

    return RenderJobBulkActionResponse(
        requested=len(job_ids),
        affected=affected,
        skipped=len(job_ids) - affected,
        jobs=results,
    )


@router.get("/render/concurrency", response_model=RenderConcurrencyResponse)
async def get_render_concurrency() -> RenderConcurrencyResponse:
    """Get current render concurrency."""

    return RenderConcurrencyResponse(concurrency=render_service.concurrency)


@router.put("/render/concurrency", response_model=RenderConcurrencyResponse)
async def set_render_concurrency(request: RenderConcurrencyRequest) -> RenderConcurrencyResponse:
    """Set current render concurrency."""

    concurrency = await render_service.set_concurrency(request.concurrency)
    return RenderConcurrencyResponse(concurrency=concurrency)


@router.get("/render/task-shutdown", response_model=TaskShutdownSettingsResponse)
async def get_task_shutdown_settings() -> TaskShutdownSettingsResponse:
    """Get the task-manager shutdown setting."""

    return TaskShutdownSettingsResponse(
        enabled=runtime_settings_service.get_shutdown_after_all_tasks(False),
        supported=power_service.supports_shutdown(),
    )


@router.put("/render/task-shutdown", response_model=TaskShutdownSettingsResponse)
async def set_task_shutdown_settings(request: TaskShutdownSettingsRequest) -> TaskShutdownSettingsResponse:
    """Enable or disable shutdown after all render tasks finish."""

    enabled = runtime_settings_service.set_shutdown_after_all_tasks(request.enabled)
    await render_service.arm_shutdown_after_all_tasks()
    return TaskShutdownSettingsResponse(
        enabled=enabled,
        supported=power_service.supports_shutdown(),
    )


@router.get("/render/logs/{job_id}", response_model=JobLogsResponse)
async def get_job_logs(job_id: str, tail: int = 100) -> JobLogsResponse:
    """Get log output for a job."""

    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Return last N lines
    log_lines = job.log_lines[-tail:] if len(job.log_lines) > tail else job.log_lines

    return JobLogsResponse(
        job_id=job.id,
        log_lines=log_lines,
        total_lines=len(job.log_lines),
    )


@router.post("/render/cancel/{job_id}")
async def cancel_job(job_id: str) -> dict:
    """Cancel a queued or running render job."""

    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    success, detail = await _cancel_render_job(job)
    if not success:
        status_code = 400 if detail in {"Job is already finished", "Job cannot be cancelled"} else 500
        raise HTTPException(status_code=status_code, detail=detail)

    await render_service.kick_queue()

    return {"job_id": job_id, "status": "cancelled"}


@router.get("/render/current", response_model=CurrentJobResponse)
async def get_current_job() -> CurrentJobResponse:
    """Get the currently running job, if any."""

    job = await job_manager.get_current_job()
    if not job:
        return CurrentJobResponse()

    return CurrentJobResponse(
        job_id=job.id,
        status=job.status.value,
        progress=JobProgressResponse(
            percent=job.progress.percent,
            current_frame=job.progress.current_frame,
            total_frames=job.progress.total_frames,
            fps=job.progress.fps,
            eta_seconds=job.progress.eta_seconds,
        ),
    )


# --- Batch Render ---


class BatchFileInput(BaseModel):
    """Input for batch render - file path with optional GPX/FIT."""

    video_path: str
    gpx_path: str | None = None
    output_path: str | None = None  # Auto-generated if not provided


class BatchRenderRequest(BaseModel):
    """Request to start batch render jobs."""

    files: list[BatchFileInput] = Field(min_length=1)
    shared_gpx_path: str | None = None
    layout: str = "default-1920x1080"
    layout_xml_path: str | None = None
    units_speed: str = DEFAULT_UNITS_SPEED
    units_altitude: str = DEFAULT_UNITS_ALTITUDE
    units_distance: str = DEFAULT_UNITS_DISTANCE
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE
    map_style: str | None = None
    gpx_merge_mode: str = DEFAULT_GPX_MERGE_MODE
    video_time_alignment: str = "auto"
    time_offset_seconds: int = 0
    ffmpeg_profile: str | None = None
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX
    language: str = DEFAULT_LANGUAGE

    @field_validator("video_time_alignment", mode="before")
    @classmethod
    def _migrate_alignment(cls, v: str | None) -> str:
        return migrate_video_time_alignment(v)


class BatchRenderResponse(BaseModel):
    """Response from batch render request."""

    batch_id: str
    job_ids: list[str]
    total_jobs: int
    skipped_files: list[str] = Field(default_factory=list)


class BatchJobDetail(BaseModel):
    """Details of a single job in batch."""

    job_id: str
    status: str
    video_name: str
    progress_percent: float = 0
    current_frame: int | None = None
    total_frames: int | None = None
    fps: float | None = None
    eta_seconds: float | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3


class BatchStatusResponse(BaseModel):
    """Response with batch status summary."""

    batch_id: str
    total: int
    pending: int
    running: int
    completed: int
    failed: int
    cancelled: int
    current_job: BatchJobDetail | None = None
    running_jobs: list[BatchJobDetail] = Field(default_factory=list)


def _calculate_batch_odo_offset(
    video_path: Path,
    gpx_path: Path,
    time_offset_seconds: int = 0,
    video_time_alignment: str = "auto",
) -> float | None:
    """Calculate odo offset for a video in a shared GPX batch.

    Extracts video creation time, applies time offset (only in "manual" alignment
    mode, matching render_service behavior), then calculates the cumulative
    distance from GPX track start to that time.

    Returns offset in meters, or None if creation time cannot be determined.
    """
    from gpstitch.services.renderer import (
        _extract_creation_time,
        _resolve_dji_filename_start_time,
        _validate_creation_time,
        calculate_odo_offset,
    )

    video_duration_sec = 0.0
    try:
        from gopro_overlay.ffmpeg import FFMPEG
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        recording = FFMPEGGoPro(FFMPEG()).find_recording(video_path)
        video_duration_sec = recording.video.duration.millis() / 1000.0
    except Exception as e:
        logger.warning("Failed to get video duration for odo offset alignment: %s", e)

    creation_time = _resolve_dji_filename_start_time(video_path, video_duration_sec, gpx_path)
    if creation_time is None:
        creation_time = _extract_creation_time(video_path)

    if creation_time is not None:
        result = _validate_creation_time(video_path, creation_time, video_duration_sec, gpx_path)
        creation_time = result.time
    else:
        logger.warning("Cannot determine creation time for %s, skipping odo offset", video_path)
        return None

    if time_offset_seconds and video_time_alignment == "manual":
        creation_time = creation_time + datetime.timedelta(seconds=time_offset_seconds)

    try:
        return calculate_odo_offset(gpx_path, creation_time)
    except Exception as e:
        logger.warning("Failed to calculate odo offset for %s: %s", video_path, e)
        return None


@router.post("/render/batch", response_model=BatchRenderResponse)
async def start_batch_render(request: BatchRenderRequest) -> BatchRenderResponse:
    """Start a batch of render jobs."""

    if not request.files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Clean up orphaned pending jobs before starting new batch
    valid_sessions = file_manager.get_all_session_ids()
    orphaned = await job_manager.cleanup_orphaned_pending_jobs(valid_sessions)
    if orphaned > 0:
        logger.info(f"Cleaned up {orphaned} orphaned pending jobs before batch start")

    batch_id = str(uuid4())
    job_ids = []
    skipped_files = []

    async def prepare_batch_job(file_input: BatchFileInput) -> tuple[str | None, str | None]:
        video_path = Path(file_input.video_path)

        # Validate video file exists
        if not video_path.exists():
            logger.warning(f"Batch: skipping non-existent file: {video_path}")
            return None, str(video_path)

        # Determine file type
        suffix = video_path.suffix.lower()
        if suffix in [".mp4", ".mov", ".avi"]:
            file_type = "video"
        elif suffix == ".gpx":
            file_type = "gpx"
        elif suffix == ".fit":
            file_type = "fit"
        elif suffix == ".srt":
            file_type = "srt"
        else:
            logger.warning(f"Batch: skipping unsupported file type: {video_path}")
            return None, str(video_path)

        # Create local session for this file (skip cleanup to preserve previous batch sessions)
        session_id = file_manager.create_local_session(skip_cleanup=True)

        try:
            # Add primary file
            video_metadata = (
                await asyncio.to_thread(extract_video_metadata, video_path) if file_type == "video" else None
            )
            gpx_fit_metadata = (
                await asyncio.to_thread(extract_gpx_fit_metadata, video_path)
                if file_type in {"gpx", "fit", "srt"}
                else None
            )
            file_manager.add_file(
                session_id=session_id,
                filename=video_path.name,
                file_path=str(video_path),
                file_type=file_type,
                role=FileRole.PRIMARY,
                video_metadata=video_metadata,
                gpx_fit_metadata=gpx_fit_metadata,
            )

            # Add secondary GPX/FIT if provided (per-file takes priority over shared)
            effective_gpx = file_input.gpx_path or request.shared_gpx_path
            gpx_path = None
            if effective_gpx:
                try:
                    gpx_path = Path(effective_gpx).expanduser().resolve()
                except (ValueError, OSError):
                    logger.warning(f"Batch: invalid GPX/FIT path: {effective_gpx}")
                    gpx_path = None
                if gpx_path and gpx_path.exists():
                    gpx_suffix = gpx_path.suffix.lower()
                    gpx_type = {".gpx": "gpx", ".fit": "fit", ".srt": "srt"}.get(gpx_suffix, "gpx")
                    secondary_metadata = await asyncio.to_thread(extract_gpx_fit_metadata, gpx_path)
                    file_manager.add_file(
                        session_id=session_id,
                        filename=gpx_path.name,
                        file_path=str(gpx_path),
                        file_type=gpx_type,
                        role=FileRole.SECONDARY,
                        gpx_fit_metadata=secondary_metadata,
                    )
                elif gpx_path:
                    logger.warning(f"Batch: GPX/FIT file not found: {gpx_path}")

            # Auto-generate output filename if not specified
            output_file = file_input.output_path
            if not output_file:
                from gpstitch.services.renderer import get_output_extension_for_profile

                ext = get_output_extension_for_profile(request.ffmpeg_profile)
                output_file = str(video_path.parent / f"{video_path.stem}_overlay{ext}")

            # Calculate odo_offset when using shared GPX (not per-file override)
            odo_offset = None
            if (
                request.shared_gpx_path
                and not file_input.gpx_path
                and file_type == "video"
                and gpx_path
                and gpx_path.exists()
            ):
                odo_offset = await asyncio.to_thread(
                    _calculate_batch_odo_offset,
                    video_path,
                    gpx_path,
                    request.time_offset_seconds,
                    request.video_time_alignment,
                )

            # Create job config
            config = RenderJobConfig(
                session_id=session_id,
                layout=request.layout,
                layout_xml_path=request.layout_xml_path,
                output_file=output_file,
                units_speed=request.units_speed,
                units_altitude=request.units_altitude,
                units_distance=request.units_distance,
                units_temperature=request.units_temperature,
                map_style=request.map_style,
                gpx_merge_mode=request.gpx_merge_mode,
                video_time_alignment=request.video_time_alignment,
                time_offset_seconds=request.time_offset_seconds,
                ffmpeg_profile=request.ffmpeg_profile,
                gps_dop_max=request.gps_dop_max,
                gps_speed_max=request.gps_speed_max,
                odo_offset=odo_offset,
                language=request.language,
            )

            # Create job with batch_id
            job = await job_manager.create_job_with_batch(config, batch_id=batch_id)
            return job.id, None

        except Exception as e:
            logger.error(f"Batch: failed to create job for {video_path}: {e}")
            # Cleanup orphaned session
            with contextlib.suppress(Exception):
                file_manager.cleanup_session(session_id)
            return None, str(video_path)

    create_concurrency = max(1, min(3, int(render_service.concurrency)))
    create_semaphore = asyncio.Semaphore(create_concurrency)

    async def prepare_limited(file_input: BatchFileInput) -> tuple[str | None, str | None]:
        async with create_semaphore:
            return await prepare_batch_job(file_input)

    results = await asyncio.gather(*(prepare_limited(file_input) for file_input in request.files))
    for job_id, skipped_file in results:
        if job_id:
            job_ids.append(job_id)
        if skipped_file:
            skipped_files.append(skipped_file)

    if not job_ids:
        raise HTTPException(status_code=400, detail="No valid files to render")

    # Start as many jobs as the render concurrency allows. This only schedules
    # render workers; it does not wait for the subprocesses to finish.
    await render_service.kick_queue()

    logger.info(f"Created batch {batch_id} with {len(job_ids)} jobs")

    return BatchRenderResponse(
        batch_id=batch_id,
        job_ids=job_ids,
        total_jobs=len(job_ids),
        skipped_files=skipped_files,
    )


@router.get("/render/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    """Get status summary of all jobs in a batch."""
    counts = await job_manager.count_batch_jobs(batch_id)

    if counts["total"] == 0:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get running job details. current_job is kept for older clients, while
    # running_jobs exposes the full concurrent state.
    running_job_details = []
    running_jobs = await job_manager.get_running_batch_jobs(batch_id)
    for running_job in running_jobs:
        video_name = "Unknown"
        primary = file_manager.get_primary_file(running_job.config.session_id)
        if primary:
            video_name = primary.filename

        running_job_details.append(
            BatchJobDetail(
                job_id=running_job.id,
                status=running_job.status.value,
                video_name=video_name,
                progress_percent=running_job.progress.percent,
                current_frame=running_job.progress.current_frame,
                total_frames=running_job.progress.total_frames,
                fps=running_job.progress.fps,
                eta_seconds=running_job.progress.eta_seconds,
                error=running_job.error,
                retry_count=running_job.retry_count,
                max_retries=running_job.max_retries,
            )
        )

    return BatchStatusResponse(
        batch_id=batch_id,
        total=counts["total"],
        pending=counts["pending"],
        running=counts["running"],
        completed=counts["completed"],
        failed=counts["failed"],
        cancelled=counts["cancelled"],
        current_job=running_job_details[0] if running_job_details else None,
        running_jobs=running_job_details,
    )


@router.post("/render/batch/{batch_id}/cancel")
async def cancel_batch(batch_id: str) -> dict:
    """Cancel all pending and running jobs in a batch."""
    counts = await job_manager.count_batch_jobs(batch_id)

    if counts["total"] == 0:
        raise HTTPException(status_code=404, detail="Batch not found")

    cancelled_count = 0
    cancelled_job_ids: set[str] = set()

    # Release any reserved/running render slots first, including jobs that are
    # still marked pending because their subprocess has not been spawned yet.
    batch_jobs = await job_manager.get_batch_jobs(batch_id)
    for job in batch_jobs:
        if job.status in (JobStatus.PENDING, JobStatus.RUNNING) and render_service.is_job_active(job.id):
            success = await render_service.cancel_render(job.id)
            if success:
                cancelled_job_ids.add(job.id)

    # Cancel all pending jobs
    pending_cancelled = await job_manager.cancel_batch_pending_jobs(batch_id)
    cancelled_count += pending_cancelled

    # Cancel running job if it belongs to this batch
    running_jobs = await job_manager.get_running_batch_jobs(batch_id)
    for running_job in running_jobs:
        if running_job.id in cancelled_job_ids:
            continue
        success = await render_service.cancel_render(running_job.id)
        if success:
            cancelled_job_ids.add(running_job.id)

    cancelled_count += len(cancelled_job_ids)
    await render_service.kick_queue()

    logger.info(f"Cancelled {cancelled_count} jobs in batch {batch_id}")

    return {
        "batch_id": batch_id,
        "cancelled_count": cancelled_count,
    }
