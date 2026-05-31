## ADDED Requirements

### Requirement: Application language can be selected
The system SHALL provide a Simplified Chinese / English language selection for the application and SHALL persist the selected language for subsequent sessions in the same browser.

#### Scenario: User switches application language
- **WHEN** the user changes the language selection between Simplified Chinese and English
- **THEN** the visible UI updates to the selected language without changing loaded files, templates, render settings, or session data
- **AND** the selected language is reused when the user reloads the application in the same browser

### Requirement: Main interface follows selected language
The system SHALL display text for the unified main interface according to the selected language, including header actions, mode names, file panels, preview states, timeline controls, status bar text, command modal text, and render entry points.

#### Scenario: User opens the main interface
- **WHEN** the user opens the unified GPStitch interface
- **THEN** the visible navigation, buttons, section titles, empty states, and status text are shown in the selected language
- **AND** internal element IDs, API fields, route paths, and persisted state keys remain unchanged

### Requirement: Configuration options follow selected language
The system SHALL show display labels and help text for render configuration, unit categories, map styles, FFmpeg profiles, GPS filters, GPX/FIT/SRT alignment options, and API-returned option metadata according to the selected language while preserving stable option values.

#### Scenario: User views render configuration
- **WHEN** the user opens the configuration panel
- **THEN** labels, hints, and option display names are shown in the selected language
- **AND** option values such as `kph`, `metre`, `osm`, `nvgpu`, and `nnvgpu` remain unchanged in API payloads

### Requirement: Advanced editor panels follow selected language
The system SHALL localize advanced mode toolbar labels, template controls, widget palette text, property panel categories, property labels, property descriptions, layer panel controls, canvas warnings, and editor empty states according to the selected language.

#### Scenario: User edits a widget in advanced mode
- **WHEN** the user switches to advanced mode and selects a widget
- **THEN** the widget name, property groups, property labels, tooltips, layer names/actions, and canvas warnings are shown in the selected language
- **AND** widget type IDs and property names saved to layout JSON/XML remain compatible with existing templates

### Requirement: OSD-facing text follows selected language
The system SHALL localize text that can appear inside previews or rendered OSD overlays according to the selected language, including default widget labels, generated text widget defaults, and metric display labels, without changing numeric telemetry values or unit conversion behavior.

#### Scenario: User previews a localized OSD layout in Chinese
- **WHEN** a preview or render contains OSD labels or default text widgets
- **AND** the selected language is Simplified Chinese
- **THEN** user-visible OSD label text is shown in Simplified Chinese
- **AND** metric keys, data binding, timestamps, coordinates, and unit conversion results remain correct

#### Scenario: User previews a localized OSD layout in English
- **WHEN** a preview or render contains OSD labels or default text widgets
- **AND** the selected language is English
- **THEN** user-visible OSD label text is shown in English
- **AND** metric keys, data binding, timestamps, coordinates, and unit conversion results remain correct

### Requirement: Preview and render carry selected language
The system SHALL pass the selected language into preview, command generation, single render, and batch render requests so OSD output uses the same language as the UI.

#### Scenario: User renders after switching language
- **WHEN** the user switches the application language and starts preview or render
- **THEN** the request sent to the backend includes the selected language
- **AND** generated OSD text in preview and final video follows that language

### Requirement: Dialogs and feedback follow selected language
The system SHALL localize modal dialogs, confirmations, GPS quality warnings, overwrite warnings, batch progress messages, error toasts, success toasts, browser alerts, and fallback messages according to the selected language.

#### Scenario: User starts batch render with warnings
- **WHEN** batch pre-check finds overwrite conflicts or GPS quality issues
- **THEN** warning dialogs, action buttons, table headings, and toast feedback are shown in the selected language
- **AND** the user can still cancel, skip, overwrite, or continue using the same behavior as before
