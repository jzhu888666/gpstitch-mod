"""Local-mode helpers for choosing and listing host files."""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import APIRouter, HTTPException

from gpstitch.config import settings
from gpstitch.models.schemas import (
    BatchDirectoryFile,
    BatchDirectoryListRequest,
    BatchDirectoryListResponse,
    LocalDirectoryDialogRequest,
    LocalDirectoryDialogResponse,
    LocalFileDialogRequest,
    LocalFileDialogResponse,
)
from gpstitch.services.localization import t

router = APIRouter(prefix="/api/local", tags=["local"])

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
GPS_EXTENSIONS = {".srt", ".gpx", ".fit"}
TELEMETRY_PRIORITY = (".srt", ".gpx", ".fit")


def _require_local_mode(language: str | None = None) -> None:
    if not settings.local_mode:
        raise HTTPException(status_code=403, detail=t("local_mode_disabled", language))


def _dialog_filetypes(file_kind: str):
    if file_kind == "video":
        return [("Video files", "*.mp4 *.mov *.avi"), ("All files", "*.*")]
    if file_kind == "gps":
        return [("GPS data files", "*.gpx *.fit *.srt"), ("All files", "*.*")]
    return [("Supported files", "*.mp4 *.mov *.avi *.gpx *.fit *.srt"), ("All files", "*.*")]


def _open_file_dialog(request: LocalFileDialogRequest) -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askopenfilename(
            title=request.title or "Select file",
            initialdir=request.initial_dir or None,
            filetypes=_dialog_filetypes(request.file_kind),
        )
    finally:
        root.destroy()
    return path or None


def _open_directory_dialog(request: LocalDirectoryDialogRequest) -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(
            title=request.title or "Select directory",
            initialdir=request.initial_dir or None,
            mustexist=True,
        )
    finally:
        root.destroy()
    return path or None


@router.post("/select-file", response_model=LocalFileDialogResponse)
async def select_local_file(request: LocalFileDialogRequest) -> LocalFileDialogResponse:
    """Open a local file picker and return the selected path."""
    _require_local_mode(request.language)

    try:
        selected = _open_file_dialog(request)
    except Exception:
        return LocalFileDialogResponse(selected=False, message=t("picker_unavailable", request.language))

    if not selected:
        return LocalFileDialogResponse(selected=False, message=t("picker_cancelled", request.language))

    return LocalFileDialogResponse(selected=True, file_path=str(Path(selected).expanduser().resolve()))


@router.post("/select-directory", response_model=LocalDirectoryDialogResponse)
async def select_local_directory(request: LocalDirectoryDialogRequest) -> LocalDirectoryDialogResponse:
    """Open a local directory picker and return the selected path."""
    _require_local_mode(request.language)

    try:
        selected = _open_directory_dialog(request)
    except Exception:
        return LocalDirectoryDialogResponse(selected=False, message=t("picker_unavailable", request.language))

    if not selected:
        return LocalDirectoryDialogResponse(selected=False, message=t("picker_cancelled", request.language))

    return LocalDirectoryDialogResponse(selected=True, directory_path=str(Path(selected).expanduser().resolve()))


@router.post("/list-directory", response_model=BatchDirectoryListResponse)
async def list_batch_directory(request: BatchDirectoryListRequest) -> BatchDirectoryListResponse:
    """List supported batch-render videos and auto-matched telemetry files."""
    _require_local_mode(request.language)

    directory = Path(request.directory_path).expanduser().resolve()
    if not directory.exists():
        raise HTTPException(status_code=404, detail=t("directory_not_found", request.language))
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=t("not_a_directory", request.language))

    files = scan_batch_directory(directory, recursive=request.recursive)
    message_key = "batch_directory_loaded" if files else "no_supported_videos"
    return BatchDirectoryListResponse(
        directory_path=str(directory),
        files=files,
        total_videos=len(files),
        message=t(message_key, request.language),
    )


def scan_batch_directory(directory: Path, recursive: bool = False) -> list[BatchDirectoryFile]:
    """Find supported videos and same-basename telemetry files."""
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    videos = sorted(
        (p for p in iterator if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda p: str(p).lower(),
    )

    return [
        BatchDirectoryFile(
            video_path=str(video),
            gpx_path=str(telemetry) if telemetry else None,
            telemetry_type=telemetry.suffix.lower().lstrip(".") if telemetry else None,
        )
        for video in videos
        for telemetry in [_find_matching_telemetry(video)]
    ]


def _find_matching_telemetry(video_path: Path) -> Path | None:
    for ext in TELEMETRY_PRIORITY:
        for candidate in (video_path.with_suffix(ext), video_path.with_suffix(ext.upper())):
            with contextlib.suppress(OSError):
                if candidate.exists() and candidate.is_file():
                    return candidate
    return None
