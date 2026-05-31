## ADDED Requirements

### Requirement: Map tiles cache under the project directory
The system SHALL store map tile cache data in a project-local directory instead of the operating system temporary directory.

#### Scenario: Preview renders a map widget
- **WHEN** a preview render uses a map widget
- **THEN** downloaded map tiles are read from and written to the configured project-local map cache directory
- **AND** the cache directory is created automatically if it does not exist

### Requirement: Preview and render share the same map cache
The system SHALL use the same project-local map cache for preview rendering and video render subprocesses.

#### Scenario: User renders after previewing the same map area
- **WHEN** map tiles were cached during preview
- **THEN** the subsequent video render uses the same cached tiles where possible
- **AND** the render subprocess does not fall back to a separate temporary cache

### Requirement: Loaded telemetry can warm map cache
After video and GPS data are loaded, the system SHALL be able to prefetch map tiles for the route area used by the selected map style and OSD map widgets.

#### Scenario: User loads video and GPS with map widgets enabled
- **WHEN** a session has usable GPS data and the selected layout includes map widgets
- **THEN** the frontend requests map cache warmup for the active session and map style
- **AND** the backend caches relevant route-area tiles within configured tile-count limits

### Requirement: Cached map tiles support offline reuse
The system SHALL reuse cached map tiles when network access is unavailable.

#### Scenario: Network is unavailable after cache warmup
- **WHEN** the map tiles for the active route area are already cached and network access fails
- **THEN** preview and render continue using cached tiles for those areas
- **AND** missing uncached tiles are reported as a non-fatal user-facing warning when possible

### Requirement: Map cache failures do not block non-map rendering
The system SHALL allow render workflows to continue when map cache warmup fails and the selected layout does not require map tiles.

#### Scenario: Cache warmup fails for a non-map layout
- **WHEN** map cache warmup fails but the selected layout has no map widgets
- **THEN** the user can still preview and render the video
- **AND** the system records or displays a localized warning instead of failing the render job

### Requirement: Map cache is bounded
The system SHALL apply limits to cache warmup work to avoid excessive network use, disk use, and UI blocking.

#### Scenario: Route spans a large area
- **WHEN** a loaded GPS track would require more tiles than the configured warmup limit
- **THEN** the system caps the warmup tile count
- **AND** the user-facing status indicates in the selected language that only part of the route was pre-cached
