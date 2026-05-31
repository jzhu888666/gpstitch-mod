## 1. Baseline Audit

- [x] 1.1 Scan unified UI, editor UI, component-generated strings, widget metadata, backend option labels, OSD-facing text, and user-facing errors for text that must support Chinese/English switching.
- [x] 1.2 Identify the current default OSD layout source for each `default-*` option and confirm where the bottom-right three data widgets are produced.
- [x] 1.3 Inspect `gopro_overlay.ffmpeg_profile.builtin_profiles` for `nvgpu` and `nnvgpu` and record required CUDA/NVENC patches.
- [x] 1.4 Inspect map renderer cache behavior in preview and wrapper subprocess render paths.

## 2. Backend Configuration And Services

- [x] 2.1 Add project-local map cache settings with automatic directory creation under the project root.
- [x] 2.2 Add local picker request/response models for selecting files, selecting directories, and listing supported directory contents.
- [x] 2.3 Implement local-mode-only picker/listing API endpoints with no filesystem mutation.
- [x] 2.4 Implement directory scanning that finds supported videos and same-basename `.srt`, `.gpx`, and `.fit` telemetry files in priority order.
- [x] 2.5 Add a map cache service that derives route bounds from video embedded GPS, DJI meta GPS, GPX, FIT, or SRT session data.
- [x] 2.6 Add bounded map cache warmup API and localized status/error messages.

## 3. Language And Localization

- [x] 3.1 Add a Chinese/English language selector, client language state, persistence, and a frontend i18n helper.
- [x] 3.2 Convert static text in `src/gpstitch/static/unified/index.html` to use the selected language.
- [x] 3.3 Convert JS-generated text in unified components including file upload, render modal, batch modal, GPS warnings, overwrite dialog, templates, timeline, mode toggle, and toasts to use the selected language.
- [x] 3.4 Convert advanced editor components including widget palette, canvas, properties panel, layers panel, template controls, and editor warnings to use the selected language.
- [x] 3.5 Localize backend option display labels for units, map styles, FFmpeg profiles, layout names, and widget metadata according to the selected language.
- [x] 3.6 Ensure API values, XML attributes, metric keys, template names, and persisted config fields remain unchanged.
- [x] 3.7 Pass selected language through preview, command generation, single render, and batch render requests.
- [x] 3.8 Ensure OSD-facing labels/default text in preview and rendered video follow the selected language.

## 4. Local File Selection UI

- [x] 4.1 Add video and GPS select buttons in local-mode single render fields while preserving manual path input fallback.
- [x] 4.2 Wire single render picker buttons to backend picker endpoints and existing `/api/local-file` session loading.
- [x] 4.3 Add batch video directory selection and shared GPS file selection controls to the batch modal.
- [x] 4.4 Populate batch file lists from selected directories and show auto-matched telemetry pairs.
- [x] 4.5 Handle picker cancellation and picker failure without changing current sessions or batch input.

## 5. Render And Telemetry Behavior

- [x] 5.1 Remove the bottom-right three widgets from GPStitch default OSD behavior without mutating saved custom templates.
- [x] 5.2 Patch or validate `nvgpu` and `nnvgpu` profile definitions so they use CUDA/NVENC-compatible settings.
- [x] 5.3 Ensure profile selection passes through command generation, single render, pre-check, and batch render.
- [x] 5.4 Ensure DJI Action embedded GPS metadata is extracted during local file loading and upload.
- [x] 5.5 Ensure preview, command generation, single render, and batch render use DJI Action embedded GPS without requiring external GPX/FIT/SRT.
- [x] 5.6 Keep external GPX/FIT/SRT merge and alignment behavior intact for single and batch render.

## 6. Map Cache Integration

- [x] 6.1 Replace preview map cache temp directory usage with the configured project-local map cache directory.
- [x] 6.2 Pass the same map cache directory into the render subprocess through wrapper environment or a library patch.
- [x] 6.3 Trigger bounded map cache warmup after session file load when the active layout contains map widgets.
- [x] 6.4 Reuse cached tiles when network access fails and show non-fatal localized warnings for missing uncached tiles.
- [x] 6.5 Add cache limit handling for large route areas.

## 7. Tests

- [x] 7.1 Add API/unit tests for local picker gating, directory listing, telemetry auto-match priority, and cancellation responses.
- [x] 7.2 Add service tests for project-local map cache path creation, route-bound extraction, warmup bounds, and offline cached-tile reuse behavior.
- [x] 7.3 Add render command/profile tests for `nvgpu`, `nnvgpu`, DJI meta GPS command handling, and external GPS regressions.
- [x] 7.4 Add tests confirming default OSD cleanup does not alter saved custom templates.
- [x] 7.5 Add frontend or e2e smoke coverage for Chinese and English quick mode, advanced mode, single picker flow, batch directory picker flow, and OSD language switching.

## 8. Verification

- [x] 8.1 Run Python unit/API tests through `.venv`.
- [x] 8.2 Run targeted e2e tests for quick mode, advanced mode, render command generation, and batch render.
- [x] 8.3 Start the local dev server and verify Chinese/English UI and OSD language switching manually in browser screenshots.
- [x] 8.4 Verify a render command with `nvgpu` and `nnvgpu` includes the expected profile and CUDA/NVENC-compatible profile definitions.
- [x] 8.5 Verify map tiles are written under the project-local cache directory and reused by preview and render.
