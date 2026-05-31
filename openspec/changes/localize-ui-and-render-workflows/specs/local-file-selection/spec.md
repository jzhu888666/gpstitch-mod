## ADDED Requirements

### Requirement: Single render supports local file picker selection
When local mode is enabled, the system SHALL allow users to select video files and GPS data files through host-machine file picker buttons instead of typing absolute paths manually.

#### Scenario: User selects a local video file
- **WHEN** local mode is enabled and the user clicks the video select button
- **THEN** the system opens a local file picker filtered to supported video formats
- **AND** after a file is selected, the system loads it through the existing session workflow and displays its metadata in the UI

#### Scenario: User selects local GPS data
- **WHEN** a video session is active and the user clicks the GPS select button
- **THEN** the system opens a local file picker filtered to GPX, FIT, and SRT files
- **AND** after a file is selected, the system attaches it as secondary telemetry for the active session

### Requirement: Picker cancellation is non-destructive
The system SHALL leave the current session and path inputs unchanged when the user cancels a local file or directory picker.

#### Scenario: User cancels file selection
- **WHEN** the local picker opens and the user cancels without selecting a file
- **THEN** no file is loaded
- **AND** the current session files, preview, and render configuration remain unchanged

### Requirement: Batch render supports video directory selection
When local mode is enabled, the system SHALL allow users to select a local video directory for batch render and automatically build a batch file list from supported video files in that directory.

#### Scenario: User selects a batch video directory
- **WHEN** the user clicks the batch video directory select button and chooses a directory
- **THEN** the system scans the directory for supported video files
- **AND** the batch modal displays the discovered videos as files to process

### Requirement: Batch render supports local GPS selection
The system SHALL allow batch render users to choose a shared GPS data file with a file picker and SHALL support per-video GPS auto-matching from the selected video directory.

#### Scenario: User selects a shared GPS file
- **WHEN** the user chooses a shared GPX, FIT, or SRT file in the batch modal
- **THEN** that path is applied as `shared_gpx_path` for all batch files that do not have a per-file override

#### Scenario: System auto-matches per-video telemetry
- **WHEN** the selected video directory contains telemetry files with the same basename as videos
- **THEN** the system associates matching `.srt`, `.gpx`, or `.fit` files with those videos
- **AND** `.srt` is preferred over `.gpx`, and `.gpx` is preferred over `.fit`

### Requirement: Manual path entry remains available
The system SHALL keep manual path entry available as a fallback for users whose environment cannot open native dialogs.

#### Scenario: Native picker is unavailable
- **WHEN** the backend cannot open a native file or directory picker
- **THEN** the UI shows a localized error explaining that manual path entry can be used
- **AND** manually typed paths continue to load and render through the existing local path APIs

### Requirement: Local picker APIs are local-mode only
The system SHALL expose file and directory picker APIs only when local mode is enabled and MUST NOT mutate or delete files while selecting or listing local paths.

#### Scenario: Local mode is disabled
- **WHEN** a client calls a local picker or directory listing API while local mode is disabled
- **THEN** the API returns a forbidden response
- **AND** no file dialog opens and no filesystem mutation occurs
