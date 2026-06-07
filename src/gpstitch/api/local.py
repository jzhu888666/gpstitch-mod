"""Local-mode helpers for choosing and listing host files."""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from gpstitch.config import settings
from gpstitch.models.schemas import (
    BatchDirectoriesListRequest,
    BatchDirectoriesListResponse,
    BatchDirectoryFile,
    BatchDirectoryListRequest,
    BatchDirectoryListResponse,
    LocalDirectoriesDialogRequest,
    LocalDirectoriesDialogResponse,
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


def _open_directories_dialog(request: LocalDirectoriesDialogRequest) -> list[str]:
    """Open a directory picker that supports multiple folders on Windows."""
    if sys.platform == "win32":
        try:
            return _open_windows_multi_directory_dialog(request)
        except Exception:
            return []

    selected = _open_directory_dialog(
        LocalDirectoryDialogRequest(
            title=request.title,
            initial_dir=request.initial_dir,
            language=request.language,
        )
    )
    return [selected] if selected else []


def _open_windows_multi_directory_dialog(request: LocalDirectoriesDialogRequest) -> list[str]:
    """Use the Windows shell dialog for multi-select folder picking."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(data1: int, data2: int, data3: int, data4: tuple[int, ...]) -> GUID:
        return GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4))

    def method(ptr: ctypes.c_void_p, index: int, restype, *argtypes):
        prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return prototype(vtable[index])

    def failed(hr: int) -> bool:
        return hr < 0

    def is_cancelled(hr: int) -> bool:
        return (hr & 0xFFFFFFFF) == 0x800704C7

    def release(ptr: ctypes.c_void_p | None) -> None:
        if ptr and ptr.value:
            method(ptr, 2, wintypes.ULONG)(ptr)

    clsid_file_open_dialog = guid(0xDC1C5A9C, 0xE88A, 0x4DDE, (0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7))
    iid_file_open_dialog = guid(0xD57C7288, 0xD4AD, 0x4768, (0xBE, 0x02, 0x9D, 0x96, 0x95, 0x32, 0xD9, 0x60))
    sigdn_filesyspath = 0x80058000
    fos_pickfolders = 0x00000020
    fos_forcefilesystem = 0x00000040
    fos_allowmultiselect = 0x00000200
    fos_pathmustexist = 0x00000800
    fos_nochangedir = 0x00000008

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    initialized = False
    init_hr = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    if init_hr >= 0:
        initialized = True
    elif (init_hr & 0xFFFFFFFF) != 0x80010106:  # RPC_E_CHANGED_MODE
        raise OSError(f"CoInitializeEx failed: {init_hr}")

    dialog = ctypes.c_void_p()
    item_array = ctypes.c_void_p()
    try:
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid_file_open_dialog),
            None,
            0x1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(iid_file_open_dialog),
            ctypes.byref(dialog),
        )
        if failed(hr):
            raise OSError(f"CoCreateInstance(FileOpenDialog) failed: {hr}")

        get_options = method(dialog, 10, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))
        set_options = method(dialog, 9, ctypes.c_long, wintypes.DWORD)
        set_title = method(dialog, 17, ctypes.c_long, wintypes.LPCWSTR)
        show = method(dialog, 3, ctypes.c_long, wintypes.HWND)
        get_results = method(dialog, 27, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))

        options = wintypes.DWORD()
        hr = get_options(dialog, ctypes.byref(options))
        if failed(hr):
            raise OSError(f"IFileDialog.GetOptions failed: {hr}")

        hr = set_options(
            dialog,
            options.value | fos_pickfolders | fos_forcefilesystem | fos_allowmultiselect | fos_pathmustexist | fos_nochangedir,
        )
        if failed(hr):
            raise OSError(f"IFileDialog.SetOptions failed: {hr}")

        if request.title:
            hr = set_title(dialog, request.title)
            if failed(hr):
                raise OSError(f"IFileDialog.SetTitle failed: {hr}")

        hr = show(dialog, None)
        if is_cancelled(hr):
            return []
        if failed(hr):
            raise OSError(f"IFileDialog.Show failed: {hr}")

        hr = get_results(dialog, ctypes.byref(item_array))
        if failed(hr):
            raise OSError(f"IFileOpenDialog.GetResults failed: {hr}")

        get_count = method(item_array, 7, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))
        get_item_at = method(item_array, 8, ctypes.c_long, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))
        count = wintypes.DWORD()
        hr = get_count(item_array, ctypes.byref(count))
        if failed(hr):
            raise OSError(f"IShellItemArray.GetCount failed: {hr}")

        paths: list[str] = []
        for index in range(count.value):
            item = ctypes.c_void_p()
            name_ptr = ctypes.c_void_p()
            try:
                hr = get_item_at(item_array, index, ctypes.byref(item))
                if failed(hr):
                    continue
                get_display_name = method(item, 5, ctypes.c_long, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))
                hr = get_display_name(item, sigdn_filesyspath, ctypes.byref(name_ptr))
                if failed(hr) or not name_ptr.value:
                    continue
                paths.append(ctypes.wstring_at(name_ptr.value))
            finally:
                if name_ptr.value:
                    ole32.CoTaskMemFree(name_ptr)
                release(item)

        return paths
    finally:
        with contextlib.suppress(Exception):
            release(item_array)
        with contextlib.suppress(Exception):
            release(dialog)
        if initialized:
            with contextlib.suppress(Exception):
                ole32.CoUninitialize()


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


@router.post("/select-directories", response_model=LocalDirectoriesDialogResponse)
async def select_local_directories(request: LocalDirectoriesDialogRequest) -> LocalDirectoriesDialogResponse:
    """Open a local directory picker and return one or more selected paths."""
    _require_local_mode(request.language)

    try:
        selected = _open_directories_dialog(request)
    except Exception:
        return LocalDirectoriesDialogResponse(selected=False, message=t("picker_unavailable", request.language))

    if not selected:
        return LocalDirectoriesDialogResponse(selected=False, message=t("picker_cancelled", request.language))

    directory_paths = [str(Path(path).expanduser().resolve()) for path in selected]
    return LocalDirectoriesDialogResponse(selected=True, directory_paths=directory_paths)


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


@router.post("/list-directories", response_model=BatchDirectoriesListResponse)
async def list_batch_directories(request: BatchDirectoriesListRequest) -> BatchDirectoriesListResponse:
    """List supported batch-render videos from multiple directories."""
    _require_local_mode(request.language)

    video_directories = [_resolve_directory(path, request.language) for path in request.directory_paths]
    gps_directories = [_resolve_directory(path, request.language) for path in request.gps_directory_paths]
    files = scan_batch_directories(video_directories, gps_directories=gps_directories, recursive=request.recursive)
    message_key = "batch_directory_loaded" if files else "no_supported_videos"
    return BatchDirectoriesListResponse(
        directory_paths=[str(path) for path in video_directories],
        gps_directory_paths=[str(path) for path in gps_directories],
        files=files,
        total_videos=len(files),
        total_matched_gps=sum(1 for file in files if file.gpx_path),
        message=t(message_key, request.language),
    )


def _resolve_directory(directory_path: str, language: str | None = None) -> Path:
    directory = Path(directory_path).expanduser().resolve()
    if not directory.exists():
        raise HTTPException(status_code=404, detail=t("directory_not_found", language))
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=t("not_a_directory", language))
    return directory


def scan_batch_directory(directory: Path, recursive: bool = False) -> list[BatchDirectoryFile]:
    """Find supported videos and same-basename telemetry files."""
    return scan_batch_directories([directory], recursive=recursive)


def scan_batch_directories(
    directories: list[Path],
    *,
    gps_directories: list[Path] | None = None,
    recursive: bool = False,
) -> list[BatchDirectoryFile]:
    """Find supported videos and match same-basename telemetry across directories."""
    video_directories = _unique_directories(directories)
    telemetry_directories = _unique_directories([*video_directories, *(gps_directories or [])])
    video_directory_names = {path.name.lower() for path in video_directories if path.name}

    telemetry_index = _build_telemetry_index(
        telemetry_directories,
        recursive=recursive,
        shallow_subdir_names=video_directory_names,
    )
    videos: list[Path] = []
    for directory in video_directories:
        videos.extend(
            p for p in _iter_directory_files(directory, recursive=recursive) if p.suffix.lower() in VIDEO_EXTENSIONS
        )

    videos = sorted(
        videos,
        key=lambda p: str(p).lower(),
    )

    return [
        BatchDirectoryFile(
            video_path=str(video),
            gpx_path=str(telemetry) if telemetry else None,
            telemetry_type=telemetry.suffix.lower().lstrip(".") if telemetry else None,
        )
        for video in videos
        for telemetry in [_find_matching_telemetry(video, telemetry_index=telemetry_index)]
    ]


def _iter_directory_files(directory: Path, recursive: bool = False):
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    return (path for path in iterator if path.is_file())


def _unique_directories(directories: list[Path]) -> list[Path]:
    unique: dict[str, Path] = {}
    for directory in directories:
        with contextlib.suppress(OSError):
            resolved = directory.expanduser().resolve()
            unique.setdefault(str(resolved).lower(), resolved)
    return list(unique.values())


def _build_telemetry_index(
    directories: list[Path],
    recursive: bool = False,
    shallow_subdir_names: set[str] | None = None,
) -> dict[str, list[Path]]:
    telemetry_by_key: dict[str, list[Path]] = {}
    for directory in directories:
        for path in _iter_telemetry_files(
            directory,
            recursive=recursive,
            shallow_subdir_names=shallow_subdir_names or set(),
        ):
            if path.suffix.lower() in GPS_EXTENSIONS:
                for key in _telemetry_match_keys(path):
                    telemetry_by_key.setdefault(key, []).append(path)

    def telemetry_sort_key(path: Path) -> tuple[int, str]:
        with contextlib.suppress(ValueError):
            return TELEMETRY_PRIORITY.index(path.suffix.lower()), str(path).lower()
        return len(TELEMETRY_PRIORITY), str(path).lower()

    for paths in telemetry_by_key.values():
        paths.sort(key=telemetry_sort_key)
    return telemetry_by_key


def _iter_telemetry_files(directory: Path, recursive: bool, shallow_subdir_names: set[str]):
    if recursive:
        yield from _iter_directory_files(directory, recursive=True)
        return

    yield from _iter_directory_files(directory, recursive=False)

    # When users select several dated video folders and one GPS root, the GPS
    # root commonly contains matching one-level folders such as 0505/0506.
    # Scan only those explicitly selected folder names to keep non-recursive
    # mode predictable.
    with contextlib.suppress(OSError):
        for child in directory.iterdir():
            if child.is_dir() and child.name.lower() in shallow_subdir_names:
                yield from _iter_directory_files(child, recursive=False)


def _find_matching_telemetry(video_path: Path, telemetry_index: dict[str, list[Path]] | None = None) -> Path | None:
    for ext in TELEMETRY_PRIORITY:
        for candidate in (video_path.with_suffix(ext), video_path.with_suffix(ext.upper())):
            with contextlib.suppress(OSError):
                if candidate.exists() and candidate.is_file():
                    return candidate
    if telemetry_index:
        for key in _video_match_keys(video_path):
            matches = telemetry_index.get(key)
            if matches:
                return matches[0]
    return None


def _telemetry_match_keys(path: Path) -> set[str]:
    keys = {path.stem.lower()}
    if path.parent.name:
        keys.add(path.parent.name.lower())
    keys.update(_date_like_keys(path.stem))
    return {key for key in keys if key}


def _video_match_keys(path: Path) -> list[str]:
    keys: list[str] = []

    def add(key: str | None) -> None:
        if key and key not in keys:
            keys.append(key)

    add(path.stem.lower())
    add(path.parent.name.lower() if path.parent.name else None)
    for parent in path.parents:
        if re.fullmatch(r"\d{4,8}", parent.name):
            add(parent.name.lower())
    for key in _date_like_keys(path.stem):
        add(key)
    return keys


def _date_like_keys(stem: str) -> set[str]:
    """Return date-ish keys used to pair DJI videos with daily GPS tracks."""
    keys: set[str] = set()
    for token in re.findall(r"\d{4,14}", stem):
        if len(token) >= 8 and token.startswith(("19", "20")):
            keys.add(token[:8].lower())
            keys.add(token[4:8].lower())
        elif len(token) >= 6:
            keys.add(token[:4].lower())
        elif len(token) == 4 and not token.startswith(("19", "20")):
            keys.add(token.lower())
    return keys
