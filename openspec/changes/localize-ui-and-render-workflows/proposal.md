## Why

GPStitch is already a local desktop-oriented video telemetry tool, but the current user-facing workflow still exposes many English-only labels, requires manual path typing in key render flows, and depends on live map tile access during preview/render. This change makes the application practical for Chinese users while preserving English operation, and makes telemetry overlay rendering more reliable when machines have intermittent network access.

## What Changes

- Add a Simplified Chinese / English language selection for the application.
- Localize the main unified interface, configuration labels, advanced editor settings, layer/property controls, dialogs, warnings, toasts, and OSD/editor-facing telemetry labels according to the selected language.
- Make preview and rendered OSD-visible default text, widget metadata, and telemetry labels follow the same selected language while preserving stable internal keys, API field names, template XML attributes, and command-line arguments.
- Add local file and directory picker workflows so single render can select video/GPS files from the host machine and batch render can select video folders plus shared or per-file GPS data without manual path typing.
- Remove the three default data widgets currently shown at the bottom-right of the default OSD layout.
- Verify and adjust the two NVGPU-related FFmpeg profiles so they use CUDA/NVENC-compatible encoding settings and are selectable from the UI.
- Ensure DJI Action videos with embedded DJI meta GPS can be loaded, previewed, and rendered with GPS data integrated through the same session/render pipeline.
- Add offline map tile caching under the project directory so the two map widgets in the upper-right OSD area can cache tiles after loading video/GPS data and continue preview/render use when the network is unavailable.

## Capabilities

### New Capabilities
- `zh-cn-localization`: Chinese/English language selection covering UI, configuration, editor, layer/property, widget metadata, OSD label, dialog, warning, and toast text.
- `local-file-selection`: Host-machine file and directory picker support for single render and batch render video/GPS selection.
- `render-telemetry-workflows`: Render behavior for default OSD cleanup, NVGPU CUDA encoding profiles, and DJI Action embedded GPS integration.
- `offline-map-cache`: Project-local offline map tile cache used by preview and render map widgets.

### Modified Capabilities

None. No existing OpenSpec capabilities are present in this repository.

## Impact

- Frontend: `src/gpstitch/static/unified/**`, `src/gpstitch/static/editor/**`, default layout/template UI, render dialogs, batch render modal, file uploader, GPS warning components, and map-related controls.
- Backend API: upload/local-file endpoints, batch render endpoints, options/config endpoints, and any new local picker and map cache endpoints needed for local desktop mode.
- Services: render command generation, file/session management, DJI meta GPS extraction, FFmpeg profile discovery/patching, map tile cache service, and template/layout generation.
- Configuration: application settings for project-local cache directories, language preference handling, localized display metadata, and FFmpeg/NVGPU profile validation.
- Tests: unit/API tests for local picker contracts and map cache service, render command tests for NVGPU/DJI/default OSD/language behavior, and e2e/UI coverage for Chinese and English single/batch render flows.
