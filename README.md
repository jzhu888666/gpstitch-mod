# gpstitch-mod

[English](README.md) | [简体中文](README.zh-CN.md)

`gpstitch-mod` is a private modified build of GPStitch for creating GPS telemetry video overlays on Windows. It focuses on batch rendering, task management, DJI/GPX time alignment, AMap rendering, and robust handling of Windows paths.

The project keeps the original package and command names:

- Python package: `gpstitch`
- Web entry point: `gpstitch`
- Render wrapper command: `gpstitch-dashboard`

## What This Build Is For

This modified build is mainly intended for these workflows:

- Batch rendering videos from multiple video folders.
- Matching one GPX/FIT folder against multiple selected video folders.
- Applying one shared GPX/FIT track to multiple videos.
- Stable alignment between DJI filename timestamps, video metadata timestamps, and GPX/FIT time ranges.
- Windows Chinese paths, `H:` drive paths, NAS paths, and `ffprobe` output compatibility.
- AMap preview and final-render map overlays.
- Background render queues with concurrency, retry, cancel, and cleanup controls.

## Major Changes

### Task Management

- Added a unified task management module for all render jobs.
- Added configurable render concurrency, currently supporting up to 3 running jobs.
- Added job selection, select all, bulk cancel, and bulk retry for failed jobs.
- Added cleanup for completed, failed, and canceled jobs.
- Moved the "shutdown after render" behavior from quick mode and batch render into task management.
- The shutdown switch now means: when enabled, the machine shuts down after all queued and running render tasks have finished.
- Added task counters for pending, running, completed, failed, and canceled jobs.

### Batch Rendering

- Fixed multi-folder video selection so selecting several folders adds them once without reopening the folder picker repeatedly.
- Fixed GPX/FIT folder selection with the same multi-selection behavior.
- Fixed batch matching when multiple video folders are selected and the selected GPX/FIT directory contains tracks for those folders.
- Preserved the shared-GPX workflow where one GPX/FIT track can be applied to one selected video folder.
- Added stronger batch pre-check behavior so invalid items are reported before rendering starts.

### Retry And Session Recovery

- Added retry support for failed jobs from task management.
- Added bulk retry for selected failed jobs.
- Stored local session file snapshots in jobs so retries can recover after frontend or backend refreshes.
- Restored local file sessions before retrying or reconstructing render requests.
- Fixed orphaned-job handling so queued retry jobs are not incorrectly marked as failed.

### Windows Paths And ffprobe JSON

- Improved handling for Windows paths containing Chinese characters and backslashes.
- Added lenient parsing for `ffprobe` JSON output that may contain invalid escape sequences.
- Improved compatibility with local files selected from drive letters, NAS paths, and long Windows paths.

### DJI And GPX/FIT Time Alignment

- Improved DJI filename timestamp handling during matching and render setup.
- Improved GPX/FIT matching against video start times.
- Preserved support for manual time offsets when video and GPS time ranges need adjustment.

### AMap Rendering

- Kept AMap-related configuration local to the user's machine.
- Improved AMap preview/final-render compatibility for the modified render workflow.
- AMap key files are not intended to be committed to this repository.

## Install And Run

Requirements:

- Windows
- Python 3.12 or newer
- FFmpeg and ffprobe available on `PATH`
- The project virtual environment at `.venv`

Start the local web app from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn gpstitch.app:app --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

## CLI Rendering

Example:

```powershell
.\.venv\Scripts\gpstitch-dashboard.exe video.mp4 output.mp4 --layout xml --layout-xml layout.xml
```

## Useful Checks

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_time_sync_api.py tests/test_render_api.py tests/test_batch_render_api.py tests/test_renderer_gpx.py
```

Run syntax checks for touched Python modules:

```powershell
.\.venv\Scripts\python.exe -m py_compile src\gpstitch\api\render.py src\gpstitch\services\job_manager.py src\gpstitch\services\file_manager.py src\gpstitch\services\renderer.py
```

## Notes

- Restart the GPStitch service after code changes.
- Old failed batch jobs can usually be retried from task management.
- AMap credentials should stay in the local user settings directory and should not be committed.
- This private modified repository is named `gpstitch-mod`.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
