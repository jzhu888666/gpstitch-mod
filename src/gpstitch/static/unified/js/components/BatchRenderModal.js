/**
 * BatchRenderModal - Batch video rendering from local file paths
 * Allows specifying multiple videos with optional GPX/FIT pairs
 */

class BatchRenderModal {
    constructor(state) {
        this.state = state;
        this.isOpen = false;
        this.batchId = null;
        this.jobIds = [];
        this.pollInterval = null;
        this.logPollInterval = null;
        this.currentJobId = null;
        this.localMode = false;
        this.selectedVideoDirs = [];
        this.selectedGpsDirs = [];
        this.directoryPickerInProgress = null;

        // Prevent overlapping requests
        this._statusRequestPending = false;
        this._logsRequestPending = false;

        this._createModal();
        this._attachEventListeners();
        this._loadLocalMode();
    }

    _createModal() {
        const modalHtml = `
            <div id="batch-render-modal" class="modal-overlay" style="display: none;">
                <div class="modal batch-modal">
                    <div class="modal-header">
                        <h3 id="batch-modal-title">Batch Render</h3>
                        <button class="modal-close" id="batch-modal-close">&times;</button>
                    </div>
                    <div class="modal-body">
                        <!-- Input View -->
                        <div id="batch-input-view">
                            <div class="form-group">
                                <label>Shared GPX/FIT Track <small>(optional)</small></label>
                                <div class="batch-picker-row">
                                    <input
                                        type="text"
                                        id="batch-shared-gpx"
                                        placeholder="/path/to/shared_track.gpx"
                                        class="form-control"
                                    />
                                    <button id="batch-select-shared-gps" class="btn btn-sm btn-secondary batch-local-picker" style="display: none;">Select Shared GPS</button>
                                </div>
                                <small class="form-hint">Single GPS track applied to all videos (e.g., Garmin watch recording)</small>
                            </div>

                            <div class="form-group">
                                <label>Time Offset <small>(seconds)</small></label>
                                <input
                                    type="number"
                                    id="batch-time-offset"
                                    value="0"
                                    step="1"
                                    class="form-control"
                                    style="width: 120px;"
                                />
                                <small class="form-hint">Adjust time alignment between video and GPS track</small>
                            </div>

                            <p class="help-text" id="batch-help-text">
                                Enter file paths, one per line.<br>
                                For video + GPX/FIT pairs, separate with comma.
                            </p>
                            <div class="batch-picker-actions batch-local-picker" style="display: none;">
                                <button id="batch-select-video-dir" class="btn btn-sm btn-secondary">Select Video Folder</button>
                                <button id="batch-select-gps-dir" class="btn btn-sm btn-secondary">Select GPS Folder</button>
                                <button id="batch-clear-dirs" class="btn btn-sm btn-secondary">Clear Folders</button>
                                <label class="checkbox-label batch-recursive-label">
                                    <input type="checkbox" id="batch-recursive-dirs">
                                    <span>Include subfolders</span>
                                </label>
                            </div>
                            <div class="batch-picker-status batch-local-picker" style="display: none;">
                                <small id="batch-directory-status" class="form-hint"></small>
                            </div>
                            <div class="form-group">
                                <label>File Paths</label>
                                <textarea
                                    id="batch-files-input"
                                    placeholder="/path/to/video1.mp4
/path/to/video2.mp4, /path/to/track2.gpx
/path/to/video3.mp4"
                                    rows="8"
                                ></textarea>
                                <small id="batch-files-hint" class="form-hint">Format: video.mp4 or video.mp4, track.gpx</small>
                            </div>

                            <div class="batch-preview">
                                <strong>Files to process: <span id="batch-file-count">0</span></strong>
                            </div>

                            <div class="batch-options">
                                <label class="checkbox-label">
                                    <input type="checkbox" id="batch-pre-checks" checked>
                                    <span>Pre-checks</span>
                                </label>
                                <small class="form-hint">Check for existing output files and GPS quality issues before starting</small>
                            </div>

                            <!-- Analyzing state -->
                            <div id="batch-analyzing" class="batch-analyzing" style="display: none;">
                                <span class="spinner-small"></span>
                                <span>Analyzing files...</span>
                            </div>
                        </div>

                        <!-- Progress View -->
                        <div id="batch-progress-view" style="display: none;">
                            <!-- Overall batch progress -->
                            <div class="batch-overall-progress">
                                <div class="progress-bar-container">
                                    <div id="batch-progress-bar" class="progress-bar"></div>
                                </div>
                                <div id="batch-progress-text" class="progress-text">
                                    0 / 0 completed
                                </div>
                            </div>

                            <div class="batch-status-summary">
                                <span class="batch-stat" id="batch-stat-pending">Pending: 0</span>
                                <span class="batch-stat" id="batch-stat-running">Running: 0</span>
                                <span class="batch-stat success" id="batch-stat-completed">Completed: 0</span>
                                <span class="batch-stat error" id="batch-stat-failed">Failed: 0</span>
                            </div>

                            <!-- Current job details -->
                            <div class="batch-current-job">
                                <div class="current-job-header">
                                    <strong>Current Job:</strong>
                                    <span id="batch-current-video">-</span>
                                </div>

                                <div class="current-job-progress">
                                    <div class="progress-bar-container small">
                                        <div id="batch-job-progress-bar" class="progress-bar"></div>
                                    </div>
                                    <span id="batch-job-percent" class="job-percent">0%</span>
                                </div>

                                <div class="render-details compact">
                                    <div class="render-detail-row">
                                        <span class="detail-label">Frame:</span>
                                        <span id="batch-job-frames" class="detail-value">-</span>
                                    </div>
                                    <div class="render-detail-row">
                                        <span class="detail-label">Speed:</span>
                                        <span id="batch-job-fps" class="detail-value">-</span>
                                    </div>
                                    <div class="render-detail-row">
                                        <span class="detail-label">ETA:</span>
                                        <span id="batch-job-eta" class="detail-value">-</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Log output -->
                            <div class="render-log-section">
                                <div class="log-header">
                                    <span>Log Output</span>
                                    <button id="batch-log-toggle" class="btn-link">Hide</button>
                                </div>
                                <pre id="batch-log-content" class="log-content"></pre>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button id="batch-cancel-btn" class="btn btn-secondary">Cancel</button>
                        <button id="batch-start-btn" class="btn btn-primary">Start Batch Render</button>
                        <button id="batch-close-btn" class="btn btn-primary" style="display: none;">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        this.modal = document.getElementById('batch-render-modal');
        this.modalTitle = document.getElementById('batch-modal-title');
        this.inputView = document.getElementById('batch-input-view');
        this.progressView = document.getElementById('batch-progress-view');
        this.filesInput = document.getElementById('batch-files-input');
        this.fileCountEl = document.getElementById('batch-file-count');
        this.progressBar = document.getElementById('batch-progress-bar');
        this.progressText = document.getElementById('batch-progress-text');
        this.startBtn = document.getElementById('batch-start-btn');
        this.cancelBtn = document.getElementById('batch-cancel-btn');
        this.closeBtn = document.getElementById('batch-close-btn');
        this.closeModalBtn = document.getElementById('batch-modal-close');

        // Stats elements
        this.statPending = document.getElementById('batch-stat-pending');
        this.statRunning = document.getElementById('batch-stat-running');
        this.statCompleted = document.getElementById('batch-stat-completed');
        this.statFailed = document.getElementById('batch-stat-failed');

        // Current job elements
        this.currentVideoEl = document.getElementById('batch-current-video');
        this.jobProgressBar = document.getElementById('batch-job-progress-bar');
        this.jobPercentEl = document.getElementById('batch-job-percent');
        this.jobFramesEl = document.getElementById('batch-job-frames');
        this.jobFpsEl = document.getElementById('batch-job-fps');
        this.jobEtaEl = document.getElementById('batch-job-eta');

        // Log elements
        this.logContent = document.getElementById('batch-log-content');
        this.logToggleBtn = document.getElementById('batch-log-toggle');

        // Pre-check elements
        this.preChecksCheckbox = document.getElementById('batch-pre-checks');
        this.analyzingEl = document.getElementById('batch-analyzing');

        // Shared GPX elements
        this.sharedGpxInput = document.getElementById('batch-shared-gpx');
        this.selectSharedGpsBtn = document.getElementById('batch-select-shared-gps');
        this.selectVideoDirBtn = document.getElementById('batch-select-video-dir');
        this.selectGpsDirBtn = document.getElementById('batch-select-gps-dir');
        this.clearDirsBtn = document.getElementById('batch-clear-dirs');
        this.recursiveDirsCheckbox = document.getElementById('batch-recursive-dirs');
        this.directoryStatusEl = document.getElementById('batch-directory-status');
        this.timeOffsetInput = document.getElementById('batch-time-offset');
        this.helpText = document.getElementById('batch-help-text');
        this.filesHint = document.getElementById('batch-files-hint');
        window.i18n?.apply(this.modal);
    }

    _attachEventListeners() {
        this.closeModalBtn.addEventListener('click', () => this._handleClose());
        this.cancelBtn.addEventListener('click', () => this._handleClose());
        this.closeBtn.addEventListener('click', () => this.close());
        this.startBtn.addEventListener('click', () => this._startBatchRender());

        this.filesInput.addEventListener('input', () => this._updateFileCount());

        this.sharedGpxInput.addEventListener('input', () => this._onSharedGpxChange());
        this.selectSharedGpsBtn?.addEventListener('click', () => this._selectSharedGps());
        this.selectVideoDirBtn?.addEventListener('click', () => this._selectDirectories('video'));
        this.selectGpsDirBtn?.addEventListener('click', () => this._selectDirectories('gps'));
        this.clearDirsBtn?.addEventListener('click', () => this._clearSelectedDirectories());
        this.recursiveDirsCheckbox?.addEventListener('change', () => this._refreshSelectedDirectories());

        this.logToggleBtn.addEventListener('click', () => {
            const isHidden = this.logContent.style.display === 'none';
            this.logContent.style.display = isHidden ? 'block' : 'none';
            this.logToggleBtn.textContent = isHidden ? 'Hide' : 'Show';
        });

        // NOTE: Overlay click close is intentionally disabled
        // Modal closes only via Cancel/Close buttons
        this.state.on('language:changed', () => window.i18n?.apply(this.modal));
    }

    async _loadLocalMode() {
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const config = await response.json();
                this.localMode = !!config.local_mode;
                this.modal.querySelectorAll('.batch-local-picker').forEach(el => {
                    el.style.display = this.localMode ? '' : 'none';
                });
            }
        } catch (error) {
            this.localMode = false;
        }
    }

    async _handleClose() {
        if (this.batchId) {
            // Batch is running - ask what to do
            const action = confirm(
                'Batch render is in progress.\n\n' +
                'OK = Cancel all remaining jobs and close\n' +
                'Cancel = Keep running in background'
            );

            if (action) {
                // User wants to cancel
                await this._cancelBatch();
                this.close();
            } else {
                // Just close, let it run
                this.close();
            }
        } else {
            this.close();
        }
    }

    async _cancelBatch() {
        if (!this.batchId) return;

        try {
            const response = await fetch(`/api/render/batch/${this.batchId}/cancel`, {
                method: 'POST',
            });

            if (response.ok) {
                const data = await response.json();
                window.toast.info(
                    `Cancelled ${data.cancelled_count} job(s)`,
                    { title: 'Batch Cancelled', duration: 3000 }
                );
            }
        } catch (error) {
            console.error('Failed to cancel batch:', error);
        }
    }

    _onSharedGpxChange() {
        const hasSharedGpx = this.sharedGpxInput.value.trim().length > 0;
        if (hasSharedGpx) {
            this.helpText.innerHTML = `${window.i18n?.t('Enter video file paths, one per line.') || 'Enter video file paths, one per line.'}<br>${window.i18n?.t('Per-file GPX pairs are ignored when shared GPX is set.') || 'Per-file GPX pairs are ignored when shared GPX is set.'}`;
            this.filesHint.textContent = window.i18n?.t('Format: video.mp4 (one per line)') || 'Format: video.mp4 (one per line)';
            this.filesInput.placeholder = '/path/to/video1.mp4\n/path/to/video2.mp4\n/path/to/video3.mp4';
        } else {
            this.helpText.innerHTML = `${window.i18n?.t('Enter file paths, one per line.') || 'Enter file paths, one per line.'}<br>${window.i18n?.t('For video + GPX/FIT pairs, separate with comma.') || 'For video + GPX/FIT pairs, separate with comma.'}`;
            this.filesHint.textContent = window.i18n?.t('Format: video.mp4 or video.mp4, track.gpx') || 'Format: video.mp4 or video.mp4, track.gpx';
            this.filesInput.placeholder = '/path/to/video1.mp4\n/path/to/video2.mp4, /path/to/track2.gpx\n/path/to/video3.mp4';
        }
        window.i18n?.apply(this.modal);
        if (this.selectedVideoDirs.length) {
            this._refreshSelectedDirectories();
        }
        this._updateFileCount();
    }

    _updateFileCount() {
        const files = this._parseFileInput();
        this.fileCountEl.textContent = files.length;
    }

    /**
     * Remove surrounding quotes from a path (single or double quotes)
     */
    _cleanPath(path) {
        if (!path) return path;
        let cleaned = path.trim();
        // Remove surrounding single or double quotes
        if ((cleaned.startsWith("'") && cleaned.endsWith("'")) ||
            (cleaned.startsWith('"') && cleaned.endsWith('"'))) {
            cleaned = cleaned.slice(1, -1);
        }
        return cleaned;
    }

    _parseFileInput() {
        const text = this.filesInput.value.trim();
        if (!text) return [];

        const hasSharedGpx = this.sharedGpxInput && this.sharedGpxInput.value.trim().length > 0;
        const lines = text.split('\n').map(l => l.trim()).filter(l => l);
        const files = [];

        for (const line of lines) {
            // Split by comma, but handle paths that might have spaces
            const parts = line.split(',').map(p => p.trim());
            const videoPath = this._cleanPath(parts[0]);

            // Skip empty paths (e.g., lines with only whitespace or quotes)
            if (!videoPath) continue;

            files.push({
                video_path: videoPath,
                // Ignore per-file GPX when shared GPX is set
                gpx_path: (!hasSharedGpx && parts[1]) ? this._cleanPath(parts[1]) : null,
            });
        }

        return files;
    }

    async _selectSharedGps() {
        try {
            const response = await fetch('/api/local/select-file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_kind: 'gps',
                    language: this.state.language || window.i18n?.getLanguage?.() || 'zh-CN'
                })
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || data.message || 'Native picker is unavailable. You can enter the path manually.');
            }
            if (!data.selected) {
                if (data.message && window.toast) window.toast.info(data.message, { duration: 2000 });
                return;
            }
            this.sharedGpxInput.value = data.file_path || '';
            this._onSharedGpxChange();
        } catch (error) {
            console.error('Shared GPS selection failed:', error);
            window.toast?.error(error.message, { title: window.i18n?.t('File Picker Failed') || 'File Picker Failed' });
        }
    }

    async _selectVideoDirectory() {
        await this._selectDirectories('video');
    }

    async _selectDirectories(kind) {
        if (this.directoryPickerInProgress) {
            return;
        }

        this.directoryPickerInProgress = kind;
        this._setDirectoryPickerBusy(true);
        try {
            const pickerResponse = await fetch('/api/local/select-directories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: kind === 'gps' ? 'Select GPS folders' : 'Select video folders',
                    language: this.state.language || window.i18n?.getLanguage?.() || 'zh-CN'
                })
            });
            const pickerData = await pickerResponse.json();
            if (!pickerResponse.ok) {
                throw new Error(pickerData.detail || pickerData.message || 'Native picker is unavailable. You can enter the path manually.');
            }
            if (!pickerData.selected) {
                if (pickerData.message && window.toast) window.toast.info(pickerData.message, { duration: 2000 });
                return;
            }

            const selectedDirs = pickerData.directory_paths || [];
            if (selectedDirs.length === 0) return;
            this._addUniqueDirectories(kind, selectedDirs);
            await this._refreshSelectedDirectories();
        } catch (error) {
            console.error('Directory selection failed:', error);
            window.toast?.error(error.message, { title: window.i18n?.t('Directory Picker Failed') || 'Directory Picker Failed' });
        } finally {
            this.directoryPickerInProgress = null;
            this._setDirectoryPickerBusy(false);
        }
    }

    _setDirectoryPickerBusy(isBusy) {
        if (this.selectVideoDirBtn) {
            this.selectVideoDirBtn.disabled = isBusy;
        }
        if (this.selectGpsDirBtn) {
            this.selectGpsDirBtn.disabled = isBusy;
        }
        if (this.clearDirsBtn) {
            this.clearDirsBtn.disabled = isBusy;
        }
    }

    async _refreshSelectedDirectories() {
        if (!this.selectedVideoDirs.length) {
            this._setDirectoryStatus('');
            return;
        }

        try {
            const multiResponse = await fetch('/api/local/list-directories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    directory_paths: this.selectedVideoDirs,
                    gps_directory_paths: this.selectedGpsDirs,
                    recursive: !!this.recursiveDirsCheckbox?.checked,
                    language: this.state.language || window.i18n?.getLanguage?.() || 'zh-CN'
                })
            });
            const listData = await multiResponse.json();
            if (!multiResponse.ok) {
                throw new Error(listData.detail || listData.message || 'Failed to list directories');
            }

            const hasSharedGpx = this.sharedGpxInput.value.trim().length > 0;
            this.filesInput.value = (listData.files || [])
                .map(file => this._formatBatchLine(file, hasSharedGpx))
                .join('\n');
            this._updateFileCount();
            this._setDirectoryStatus(this._formatDirectoryStatus(listData));
            if (window.toast && listData.message) {
                window.toast.success(`${listData.message} ${listData.total_videos || 0}`, {
                    title: window.i18n?.t('Batch Directory') || 'Batch Directory',
                    duration: 3000
                });
            }
        } catch (error) {
            console.error('Directory scan failed:', error);
            window.toast?.error(error.message, { title: window.i18n?.t('Directory Picker Failed') || 'Directory Picker Failed' });
        }
    }

    _addUniqueDirectories(kind, paths) {
        const target = kind === 'gps' ? this.selectedGpsDirs : this.selectedVideoDirs;
        const existing = new Set(target.map(path => path.toLowerCase()));
        for (const path of paths) {
            if (!path || existing.has(path.toLowerCase())) continue;
            target.push(path);
            existing.add(path.toLowerCase());
        }
    }

    _clearSelectedDirectories() {
        this.selectedVideoDirs = [];
        this.selectedGpsDirs = [];
        this.filesInput.value = '';
        this._updateFileCount();
        this._setDirectoryStatus('');
    }

    _setDirectoryStatus(text) {
        if (this.directoryStatusEl) {
            this.directoryStatusEl.textContent = text || '';
        }
    }

    _formatDirectoryStatus(data) {
        const videoDirs = this.selectedVideoDirs.length;
        const gpsDirs = this.selectedGpsDirs.length;
        const videos = data.total_videos || 0;
        const matchedGps = data.total_matched_gps || 0;
        return `${videoDirs} video folder(s), ${gpsDirs} GPS folder(s), ${videos} video(s), ${matchedGps} matched GPS`;
    }

    _formatBatchLine(file, hasSharedGpx) {
        if (!file?.video_path) return '';
        if (!hasSharedGpx && file.gpx_path) {
            return `${file.video_path}, ${file.gpx_path}`;
        }
        return file.video_path;
    }

    /**
     * Check if layout is a predefined one (not custom template)
     */
    _isPredefinedLayout(layout) {
        return layout.startsWith('default-') || layout.startsWith('speed-awareness');
    }

    /**
     * Generate output path for a video file
     */
    _generateOutputPath(videoPath) {
        const lastForwardSlash = videoPath.lastIndexOf('/');
        const lastBackSlash = videoPath.lastIndexOf('\\');
        const lastSlash = Math.max(lastForwardSlash, lastBackSlash);
        const lastDot = videoPath.lastIndexOf('.');
        const dir = lastSlash > -1 ? videoPath.substring(0, lastSlash) : '.';
        const name = videoPath.substring(lastSlash + 1, lastDot > lastSlash ? lastDot : undefined);
        const sep = lastBackSlash > lastForwardSlash ? '\\' : '/';
        return `${dir}${sep}${name}_overlay.mp4`;
    }

    async _startBatchRender() {
        let files = this._parseFileInput();

        if (files.length === 0) {
            window.toast.error('Please enter at least one file path', { title: 'No Files' });
            return;
        }

        const preChecksEnabled = this.preChecksCheckbox?.checked ?? true;

        // Show analyzing state
        this.startBtn.disabled = true;

        try {
            // Run pre-checks if enabled
            if (preChecksEnabled) {
                this.startBtn.textContent = window.i18n?.t('Analyzing...') || 'Analyzing...';
                this.analyzingEl.style.display = 'flex';

                // Call pre-check API (overwrite + GPS quality check)
                const preCheck = await this._preCheckFiles(files);

                this.analyzingEl.style.display = 'none';

                // 1. Handle overwrite conflicts
                if (preCheck.overwrite_conflicts && preCheck.overwrite_conflicts.length > 0) {
                    const existingPaths = preCheck.overwrite_conflicts.map(c => c.output_path);
                    let decision;

                    if (window.overwriteConfirmDialog) {
                        decision = await window.overwriteConfirmDialog.show(
                            existingPaths,
                            { showSkip: true }
                        );
                    } else {
                        // Fallback to browser confirm
                        const fileList = existingPaths.slice(0, 5).join('\n');
                        const more = existingPaths.length > 5
                            ? `\n...and ${existingPaths.length - 5} more` : '';
                        decision = confirm(`${existingPaths.length} file(s) already exist:\n${fileList}${more}\n\nOverwrite all?`)
                            ? 'overwrite' : null;
                    }

                    if (decision === null) {
                        // User cancelled
                        return;
                    }

                    if (decision === 'skip') {
                        // Filter out files with overwrite conflicts
                        const conflictVideoPaths = new Set(
                            preCheck.overwrite_conflicts.map(c => c.video_path)
                        );
                        files = files.filter(f => !conflictVideoPaths.has(this._resolvePath(f.video_path)));

                        if (files.length === 0) {
                            window.toast.info('All output files already exist. Nothing to render.', {
                                title: 'No Files to Process'
                            });
                            return;
                        }

                        window.toast.info(
                            `Skipping ${preCheck.overwrite_conflicts.length} existing file(s)`,
                            { title: 'Files Skipped', duration: 3000 }
                        );
                    }
                }

                // 2. Show GPS quality table
                // Filter GPS files to only include files still in the list
                const remainingVideoPaths = new Set(files.map(f => this._resolvePath(f.video_path)));
                const remainingGpsFiles = (preCheck.gps_files || []).filter(
                    file => remainingVideoPaths.has(file.video_path)
                );

                // Count issues in remaining files
                const remainingIssuesCount = remainingGpsFiles.filter(
                    f => ['poor', 'no_signal'].includes(f.quality_score)
                ).length;

                // Always show GPS quality dialog
                if (remainingGpsFiles.length > 0) {
                    let decision;

                    if (window.gpsBatchWarningDialog) {
                        decision = await window.gpsBatchWarningDialog.show(
                            remainingGpsFiles,
                            { issuesCount: remainingIssuesCount }
                        );
                    } else {
                        // Fallback to browser confirm
                        if (remainingIssuesCount > 0) {
                            const issueFiles = remainingGpsFiles
                                .filter(f => ['poor', 'no_signal'].includes(f.quality_score))
                                .slice(0, 5)
                                .map(i => i.video_path.split('/').pop())
                                .join('\n');
                            decision = confirm(
                                `${remainingIssuesCount} file(s) have poor GPS:\n${issueFiles}\n\nRender anyway?`
                            ) ? 'render_all' : null;
                        } else {
                            decision = 'render_all';
                        }
                    }

                    if (decision === null) {
                        // User cancelled
                        return;
                    }

                    if (decision === 'skip') {
                        // Filter out files with GPS issues
                        const issueVideoPaths = new Set(
                            remainingGpsFiles
                                .filter(f => ['poor', 'no_signal'].includes(f.quality_score))
                                .map(f => f.video_path)
                        );
                        files = files.filter(f => !issueVideoPaths.has(this._resolvePath(f.video_path)));

                        if (files.length === 0) {
                            window.toast.info('No files remaining to render.', {
                                title: 'All Files Skipped'
                            });
                            return;
                        }

                        window.toast.info(
                            `Skipping ${remainingIssuesCount} file(s) with poor GPS`,
                            { title: 'Files Skipped', duration: 3000 }
                        );
                    }
                    // If 'render_all', continue with all files
                }
            }

            // 3. Execute batch render with remaining files
            await this._executeBatchRender(files);

        } catch (error) {
            console.error('Batch render failed:', error);
            window.toast.error(error.message, { title: 'Batch Render Failed' });
        } finally {
            this.startBtn.disabled = false;
            this.startBtn.textContent = window.i18n?.t('Start Batch Render') || 'Start Batch Render';
            this.analyzingEl.style.display = 'none';
        }
    }

    /**
     * Resolve path to absolute form (approximation for comparison)
     * Note: Backend returns resolved paths, frontend paths may not be resolved
     */
    _resolvePath(path) {
        // Remove quotes and normalize
        let cleaned = this._cleanPath(path);
        // Expand ~ to absolute (best effort, actual expansion done by backend)
        if (cleaned.startsWith('~')) {
            // We can't know the actual home dir, but backend will resolve it
            // For comparison purposes, we'll keep it as-is
        }
        return cleaned;
    }

    /**
     * Call pre-check API to get overwrite conflicts and GPS issues
     */
    async _preCheckFiles(files) {
        const payload = {
            files: files,
            ffmpeg_profile: this.state.quickConfig?.ffmpegProfile || null
        };
        const sharedGpx = this.sharedGpxInput?.value?.trim();
        if (sharedGpx) {
            payload.shared_gpx_path = sharedGpx;
        }
        const response = await fetch('/api/render/pre-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Pre-check failed');
        }

        return await response.json();
    }

    /**
     * Execute batch render with the given files
     */
    async _executeBatchRender(files) {
        let layout = 'default';
        let layoutXmlPath = null;

        // Get layout based on current mode
        if (this.state.mode === 'quick') {
            // Quick mode: use quickConfig.layout
            const layoutName = this.state.quickConfig?.layout || 'default-1920x1080';

            if (!this._isPredefinedLayout(layoutName)) {
                // Custom template in quick mode
                const templateService = new TemplateService();
                const pathResponse = await templateService.getTemplatePath(layoutName);
                layout = 'xml';
                layoutXmlPath = pathResponse.file_path;
            } else {
                layout = layoutName;
            }
        } else {
            // Advanced mode: get from TemplateManager
            const templateManager = window.app?.modeToggle?.templateManager;
            const selectedTemplate = templateManager?.getSelectedTemplate();

            if (selectedTemplate && selectedTemplate.type === 'custom') {
                // Custom template: get file path from backend
                const templateService = new TemplateService();
                const pathResponse = await templateService.getTemplatePath(selectedTemplate.name);
                layout = 'xml';
                layoutXmlPath = pathResponse.file_path;
            } else if (selectedTemplate && selectedTemplate.type === 'predefined') {
                layout = selectedTemplate.name;
            } else {
                throw new Error('Please select a template first.');
            }
        }

        // Get shared GPX and time offset from batch modal inputs
        const sharedGpxPath = this.sharedGpxInput.value.trim() || null;
        const batchTimeOffset = parseInt(this.timeOffsetInput.value, 10) || 0;

        const request = {
            files: files,
            shared_gpx_path: sharedGpxPath,
            layout: layout,
            layout_xml_path: layoutXmlPath,
            units_speed: this.state.quickConfig?.unitsSpeed || 'kph',
            units_altitude: this.state.quickConfig?.unitsAltitude || 'metre',
            units_distance: this.state.quickConfig?.unitsDistance || 'km',
            units_temperature: this.state.quickConfig?.unitsTemperature || 'degC',
            map_style: this.state.quickConfig?.mapStyle || 'osm',
            gpx_merge_mode: this.state.quickConfig?.gpxMergeMode || 'OVERWRITE',
            video_time_alignment: this.state.quickConfig?.videoTimeAlignment || 'auto',
            time_offset_seconds: batchTimeOffset,
            ffmpeg_profile: this.state.quickConfig?.ffmpegProfile || null,
            gps_dop_max: this.state.quickConfig?.gpsDopMax || 20,
            gps_speed_max: this.state.quickConfig?.gpsSpeedMax || 200,
            language: this.state.language || window.i18n?.getLanguage?.() || 'zh-CN',
        };

        this.startBtn.textContent = window.i18n?.t('Starting...') || 'Starting...';

        const response = await fetch('/api/render/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start batch render');
        }

        const data = await response.json();
        this.batchId = data.batch_id;
        this.jobIds = data.job_ids;
        document.dispatchEvent(new CustomEvent('render-queue:changed', {
            detail: {
                source: 'batch',
                batchId: this.batchId,
                jobIds: this.jobIds,
            }
        }));

        // Show warning for skipped files
        if (data.skipped_files && data.skipped_files.length > 0) {
            window.toast.warning(
                `${data.skipped_files.length} file(s) skipped: ${data.skipped_files.join(', ')}`,
                { title: 'Some Files Skipped', duration: 5000 }
            );
        }

        window.toast.success(
            `Batch render started: ${data.total_jobs} jobs queued`,
            { title: 'Batch Started', duration: 3000 }
        );

        // Switch to progress view
        this._showProgressView();
        this._startPolling();
    }

    _showProgressView() {
        this.inputView.style.display = 'none';
        this.progressView.style.display = 'block';
        this.startBtn.style.display = 'none';
        this.cancelBtn.textContent = window.i18n?.t('Cancel') || 'Cancel';
        this.modalTitle.textContent = window.i18n?.t('Batch Render Progress') || 'Batch Render Progress';
        window.i18n?.apply(this.modal);
    }

    _showInputView() {
        this.inputView.style.display = 'block';
        this.progressView.style.display = 'none';
        this.startBtn.style.display = 'inline-block';
        this.closeBtn.style.display = 'none';
        this.cancelBtn.textContent = window.i18n?.t('Cancel') || 'Cancel';
        this.modalTitle.textContent = window.i18n?.t('Batch Render') || 'Batch Render';
        this.startBtn.textContent = window.i18n?.t('Start Batch Render') || 'Start Batch Render';
        window.i18n?.apply(this.modal);
    }

    _startPolling() {
        this._stopPolling();
        this.pollInterval = setInterval(() => this._updateStatus(), 2000);
        this.logPollInterval = setInterval(() => this._updateLogs(), 3000);
        this._updateStatus();
    }

    _stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        if (this.logPollInterval) {
            clearInterval(this.logPollInterval);
            this.logPollInterval = null;
        }
    }

    async _updateStatus() {
        if (!this.batchId || !this.isOpen) return;

        // Skip if previous request is still pending
        if (this._statusRequestPending) return;

        this._statusRequestPending = true;
        try {
            const response = await fetch(`/api/render/batch/${this.batchId}/status`);
            if (!response.ok) return;

            const status = await response.json();
            this._updateUI(status);

            // Track current job for logs
            if (status.current_job) {
                this.currentJobId = status.current_job.job_id;
            }

            // Stop polling if all jobs are terminal
            const terminal = status.completed + status.failed + status.cancelled;
            if (terminal >= status.total) {
                this._stopPolling();
                this.cancelBtn.style.display = 'none';
                this.closeBtn.style.display = 'inline-block';

                // Show summary toast
                if (status.failed > 0) {
                    window.toast.warning(
                        `${status.completed} completed, ${status.failed} failed`,
                        { title: 'Batch Complete', duration: 5000 }
                    );
                } else {
                    window.toast.success(
                        `All ${status.completed} videos rendered successfully`,
                        { title: 'Batch Complete', duration: 5000 }
                    );
                }
            }

        } catch (error) {
            console.error('Failed to update batch status:', error);
        } finally {
            this._statusRequestPending = false;
        }
    }

    async _updateLogs() {
        if (!this.currentJobId || !this.isOpen) return;

        // Skip if previous request is still pending
        if (this._logsRequestPending) return;

        this._logsRequestPending = true;
        try {
            const response = await fetch(`/api/render/logs/${this.currentJobId}?tail=100`);
            if (!response.ok) return;

            const data = await response.json();
            if (data.log_lines && data.log_lines.length > 0) {
                this.logContent.textContent = data.log_lines.join('\n');
                // Auto-scroll to bottom
                this.logContent.scrollTop = this.logContent.scrollHeight;
            }
        } catch (error) {
            // Silently ignore log fetch errors
        } finally {
            this._logsRequestPending = false;
        }
    }

    _updateUI(status) {
        // Update overall progress bar
        const overallPercent = status.total > 0
            ? ((status.completed + status.failed + status.cancelled) / status.total) * 100
            : 0;
        this.progressBar.style.width = `${overallPercent}%`;

        // Add color class based on status
        this.progressBar.classList.remove('success', 'error');
        if (status.running === 0 && status.pending === 0) {
            if (status.failed > 0) {
                this.progressBar.classList.add('error');
            } else {
                this.progressBar.classList.add('success');
            }
        }

        // Update progress text
        this.progressText.textContent =
            `${status.completed} / ${status.total} completed`;

        // Update stats
        this.statPending.textContent = `Pending: ${status.pending}`;
        this.statRunning.textContent = `Running: ${status.running}`;
        this.statCompleted.textContent = `Completed: ${status.completed}`;
        this.statFailed.textContent = `Failed: ${status.failed}`;

        // Update current job details
        if (status.current_job) {
            const job = status.current_job;
            this.currentVideoEl.textContent = job.video_name;

            // Job progress bar
            this.jobProgressBar.style.width = `${job.progress_percent}%`;
            this.jobPercentEl.textContent = `${Math.round(job.progress_percent)}%`;

            // Frames
            if (job.current_frame) {
                const framesText = job.total_frames
                    ? `${job.current_frame} / ${job.total_frames}`
                    : `${job.current_frame}`;
                this.jobFramesEl.textContent = framesText;
            } else {
                this.jobFramesEl.textContent = '-';
            }

            // FPS
            if (job.fps) {
                this.jobFpsEl.textContent = `${job.fps.toFixed(1)} frames/s`;
            } else {
                this.jobFpsEl.textContent = '-';
            }

            // ETA
            if (job.eta_seconds) {
                this.jobEtaEl.textContent = this._formatEta(job.eta_seconds);
            } else {
                this.jobEtaEl.textContent = '-';
            }
        } else if (status.pending > 0) {
            this.currentVideoEl.textContent = 'Starting next job...';
            this._resetJobDetails();
        } else {
            this.currentVideoEl.textContent = 'All jobs finished';
            this._resetJobDetails();
        }
    }

    _resetJobDetails() {
        this.jobProgressBar.style.width = '0%';
        this.jobPercentEl.textContent = '0%';
        this.jobFramesEl.textContent = '-';
        this.jobFpsEl.textContent = '-';
        this.jobEtaEl.textContent = '-';
    }

    _formatEta(seconds) {
        if (!seconds || seconds <= 0) return '-';
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        if (hours > 0) {
            return `${hours}h ${mins}m ${secs}s`;
        } else if (mins > 0) {
            return `${mins}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }

    open() {
        this.isOpen = true;
        this.modal.style.display = 'flex';
        this.batchId = null;
        this.jobIds = [];
        this.currentJobId = null;
        this.selectedVideoDirs = [];
        this.selectedGpsDirs = [];
        this._statusRequestPending = false;
        this._logsRequestPending = false;
        this.sharedGpxInput.value = '';
        this.timeOffsetInput.value = '0';
        if (this.recursiveDirsCheckbox) {
            this.recursiveDirsCheckbox.checked = false;
        }
        this._setDirectoryStatus('');
        this._onSharedGpxChange();
        this.filesInput.value = '';
        this._updateFileCount();
        this._showInputView();
        this._resetProgress();
    }

    _resetProgress() {
        this.progressBar.style.width = '0%';
        this.progressBar.classList.remove('success', 'error');
        this.progressText.textContent = '0 / 0 completed';
        this.statPending.textContent = 'Pending: 0';
        this.statRunning.textContent = 'Running: 0';
        this.statCompleted.textContent = 'Completed: 0';
        this.statFailed.textContent = 'Failed: 0';
        this.currentVideoEl.textContent = '-';
        this._resetJobDetails();
        this.logContent.textContent = '';
        this.logContent.style.display = 'block';
        this.logToggleBtn.textContent = 'Hide';
    }

    close() {
        this.isOpen = false;
        this.modal.style.display = 'none';
        this._stopPolling();
        this.batchId = null;
        this.jobIds = [];
        this.currentJobId = null;
    }
}

window.BatchRenderModal = BatchRenderModal;
