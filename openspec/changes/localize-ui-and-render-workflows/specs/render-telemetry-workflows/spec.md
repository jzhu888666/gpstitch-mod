## ADDED Requirements

### Requirement: Default OSD omits bottom-right data widgets
The system SHALL remove the three data widgets shown in the bottom-right area of the default OSD layout while preserving the rest of the default layout behavior.

#### Scenario: User previews the default OSD
- **WHEN** the user selects a default OSD layout and generates a preview
- **THEN** the bottom-right three data widgets are not present
- **AND** remaining default map, path, telemetry, and video overlay elements continue to render

### Requirement: Custom templates preserve user-added data widgets
The system SHALL NOT remove data widgets from saved custom templates unless the user edits those templates.

#### Scenario: User renders an existing custom template
- **WHEN** a saved custom template contains bottom-right data widgets
- **THEN** the system renders the template as saved
- **AND** the default OSD cleanup does not mutate the custom template file

### Requirement: NVGPU profiles use CUDA-compatible encoding
The system SHALL ensure the `nvgpu` and `nnvgpu` FFmpeg profiles are valid NVIDIA GPU profiles that use NVENC hardware encoding and, for the CUDA overlay profile, CUDA-compatible processing settings.

#### Scenario: User selects NVIDIA GPU profile
- **WHEN** the user selects `nvgpu` or `nnvgpu` and starts render command generation or rendering
- **THEN** the selected profile is passed to the render command
- **AND** the profile definition includes NVIDIA hardware encoding settings compatible with CUDA/NVENC-capable FFmpeg builds

### Requirement: NVGPU profile feedback is localized
The system SHALL show localized display names/descriptions for NVGPU profiles and SHALL surface render failures caused by unavailable NVIDIA hardware, drivers, or FFmpeg support in the selected user-facing language.

#### Scenario: GPU encoding is unavailable at runtime
- **WHEN** a render using `nvgpu` or `nnvgpu` fails because FFmpeg lacks required NVIDIA support
- **THEN** the user-facing error explains in the selected language that NVIDIA GPU/CUDA/NVENC support is unavailable or misconfigured
- **AND** the failure does not corrupt the source video, GPS data, or saved template

### Requirement: DJI Action embedded GPS loads into sessions
The system SHALL detect DJI Action videos with embedded DJI meta GPS during local file selection, upload, and batch session creation, and SHALL mark the session as having usable GPS data.

#### Scenario: User loads a DJI Action video
- **WHEN** the selected video contains a DJI meta GPS stream
- **THEN** the session file metadata indicates embedded DJI GPS is available
- **AND** the UI shows that GPS data is present without requiring a separate GPX/FIT/SRT file

### Requirement: DJI Action embedded GPS renders correctly
The system SHALL integrate DJI Action embedded GPS into preview, command generation, single render, and batch render workflows.

#### Scenario: User renders a DJI Action video without external GPS
- **WHEN** a session contains a DJI Action video with embedded GPS and no secondary GPS file
- **THEN** preview and render use the embedded DJI GPS data
- **AND** the generated command includes the DJI meta source handling required by the GPStitch wrapper

### Requirement: External GPS remains supported with video workflows
The system SHALL continue to support video plus external GPX, FIT, or SRT data in single and batch render workflows after the localization and picker changes.

#### Scenario: User renders video with external GPX
- **WHEN** the user loads a video and attaches an external GPX, FIT, or SRT file
- **THEN** preview, command generation, and render use the external telemetry according to the selected alignment and merge options
- **AND** existing GPS quality checks and time offset behavior remain available
