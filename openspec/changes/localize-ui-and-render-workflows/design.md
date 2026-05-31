## Context

GPStitch is a local-first FastAPI application with a static browser UI. It already supports local path sessions (`/api/local-file`, `/api/local-file-secondary`), batch render jobs, DJI SRT/DJI meta GPS conversion, FFmpeg profile selection, advanced template editing, and preview rendering through `gopro-overlay`.

The requested change spans user-facing frontend text, backend option metadata, render command generation, native file/directory selection, default layout behavior, OSD language switching, and map tile caching. The browser cannot expose host absolute paths through normal `<input type="file">`; therefore true local selection must be initiated by the Python backend while local mode is enabled.

## Goals / Non-Goals

**Goals:**
- Provide Simplified Chinese and English text for the main UI, configuration panels, advanced editor controls, layer/property panels, dialogs, warnings, toasts, widget metadata, and OSD-facing labels.
- Add a single application language selection that controls both UI language and OSD language.
- Preserve stable internal identifiers: API field names, unit/profile values, metric keys, XML attributes, template filenames, and CLI flags remain compatible.
- Replace manual path typing in local mode with file and directory chooser actions for single render and batch render.
- Keep typed path input as a fallback for environments where a native dialog cannot be opened.
- Remove the three bottom-right default data widgets from default OSD layouts while keeping existing custom templates valid.
- Validate that `nvgpu` and `nnvgpu` use NVENC/CUDA-capable settings and expose useful localized display descriptions.
- Ensure DJI Action embedded meta GPS follows the same load, preview, render, and batch render path as other GPS sources.
- Move map tile caching to a project-local cache directory and share it across preview and render subprocesses.

**Non-Goals:**
- Translating logs, Python source comments, exception class names, or internal API contracts unless the text is shown directly to users.
- Guaranteeing map tiles exist for every future zoom/viewport; the cache must warm likely tiles and reuse cached tiles offline.
- Shipping FFmpeg, NVIDIA drivers, CUDA runtime, or GPU hardware detection beyond profile validation and clear failure messages.

## Decisions

1. Use a small shared localization layer for browser text, backend-localized option metadata, and OSD labels.

   Static HTML and JS-created strings will use a lightweight `i18n` helper with `zh-CN` and `en` catalogs. Backend endpoints that return user-visible labels (`/api/options/units`, `/api/options/map-styles`, `/api/options/ffmpeg-profiles`, widget metadata) will return localized labels/descriptions while keeping values such as `kph`, `osm`, `nvgpu`, and `speed` unchanged. Preview and render requests will carry the selected language so generated/default OSD text follows the same setting.

   Alternative considered: translating only the visible HTML/JS to Chinese. That would leave English mode and rendered OSD language inconsistent with the system selection.

2. Persist language on the client and pass it explicitly to backend calls that produce display text or OSD output.

   The selected language will be stored in local storage and reflected in a header control. The frontend will pass the language as a query parameter/header for option metadata and as a request field for preview, command generation, single render, and batch render. Backend defaults remain conservative (`zh-CN` for the localized product UI unless an English selection is sent).

3. Implement local picker APIs in the backend for local mode.

   Add endpoints such as `/api/local/select-file`, `/api/local/select-directory`, and `/api/local/list-directory`. File selection will accept a file kind (`video`, `gps`, or `any-supported`) and return a resolved absolute path or cancellation. Directory listing will scan supported video files and optional matching GPS/SRT files so batch render can populate the job list without manual path entry.

   Alternative considered: HTML file inputs or drag/drop. They work for upload mode but do not expose reliable absolute paths, so they cannot satisfy local path rendering without copying files.

4. Keep local picker access gated and conservative.

   Picker and directory listing APIs will be available only when `GPSTITCH_LOCAL_MODE=true`. They should not accept arbitrary destructive actions and should return paths only for explicit user selections. Existing typed local path support remains to avoid blocking headless or remote browser usage.

5. Use project-local map cache as the single cache root.

   Add a configurable setting such as `map_cache_dir`, defaulting to a directory under the project root, for example `.gpstitch-cache/maps`. Preview rendering will use this directory instead of the system temp directory. Render subprocesses launched through the GPStitch wrapper will receive the same cache directory through an environment variable or wrapper patch so `gopro-overlay` map rendering shares cached tiles.

   Alternative considered: keeping the existing temp cache. That does not meet the requirement because temp cleanup and network failures can break repeat render sessions.

6. Warm map tiles from loaded session telemetry.

   When video/GPS data is loaded and the selected layout/style includes map widgets, the frontend will request cache warmup for the session. The backend will derive the GPS bounds/time range from the primary embedded GPS, DJI meta GPS, or secondary GPX/FIT/SRT and prefetch a bounded set of likely map tiles for the selected map style. Preview/render will still lazily fill missing tiles.

7. Shadow or generate default OSD layouts rather than changing internal metric keys.

   Remove the bottom-right three default data widgets by using GPStitch-owned default layout XML where necessary, or by adjusting local default template generation. Existing custom templates and advanced editor widgets continue to support those metrics if the user adds them intentionally. Default text widgets and metric labels generated by GPStitch-owned layouts will use the selected language at preview/render time.

8. Validate GPU profiles at the profile-definition boundary.

   The two NVGPU-related profiles will be checked against `gopro_overlay.ffmpeg_profile.builtin_profiles` and patched if necessary so the encoder path uses NVIDIA hardware encoding (`h264_nvenc` or equivalent) and the CUDA overlay profile keeps CUDA-related input/filter settings. Tests will assert generated commands include the selected profile and that patched profile definitions contain NVENC/CUDA markers.

## Risks / Trade-offs

- Native dialogs may fail in service/headless contexts -> keep typed path fallback and return a localized error when the picker cannot open.
- Local picker APIs expose host paths in local mode -> restrict to local mode, no file mutation, and only return paths selected or scanned by the user.
- Map providers can change tile URL policies or require API keys -> cache warmup must respect existing map style metadata and surface API-key/network failures without blocking non-map rendering.
- Full UI localization can miss dynamically generated text -> add targeted tests and scan common static/JS files for remaining hard-coded user-facing strings after implementation.
- NVENC availability depends on user hardware, driver, and FFmpeg build -> validate profile definitions and report runtime failures clearly, but do not try to install drivers.
- Prefetching too many map tiles can be slow or large -> cap zoom levels/tile counts and cache only the session route area required by current layouts.

## Migration Plan

1. Add language catalogs, localized labels, and picker/cache settings without changing API values.
2. Add local picker and map cache endpoints with tests.
3. Update frontend components to use the language helper and picker buttons while preserving typed path fallback.
4. Update preview/render/profile/map cache integration and default layout behavior so OSD text follows the selected language.
5. Run unit/API tests, targeted render command tests, and UI smoke/e2e tests for Chinese and English quick mode, advanced mode, and batch render.
6. Rollback can hide the language/picker/cache warmup UI while existing typed local path and render endpoints continue to work.

## Open Questions

- The exact project-local map cache directory name can be `.gpstitch-cache/maps` unless a visible directory name is preferred.
- If a selected batch directory contains multiple possible GPS files per video, the first implementation should prefer same-basename `.srt`, then `.gpx`, then `.fit`, matching current auto-detection.
