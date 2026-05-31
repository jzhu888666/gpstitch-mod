/**
 * GPSBatchWarningDialog - Shows GPS quality table for batch files
 * Displays all files with their GPS status, highlights issues
 */

class GPSBatchWarningDialog {
    constructor() {
        this.resolvePromise = null;
        this._createModal();
        this._attachEventListeners();
    }

    _createModal() {
        const modalHtml = `
            <div id="gps-batch-warning-modal" class="modal-overlay" style="display: none;">
                <div class="modal gps-batch-warning-modal">
                    <div class="modal-header">
                        <h3 id="gps-batch-warning-title">GPS Quality Check</h3>
                    </div>
                    <div class="modal-body">
                        <p id="gps-batch-warning-message" class="gps-batch-message"></p>
                        <div class="gps-batch-table-container">
                            <table id="gps-batch-table" class="gps-batch-table">
                                <thead>
                                    <tr>
                                        <th>File</th>
                                        <th>GPS Quality</th>
                                        <th>Usable</th>
                                        <th>DOP</th>
                                    </tr>
                                </thead>
                                <tbody id="gps-batch-table-body">
                                </tbody>
                            </table>
                        </div>
                        <p id="gps-batch-hint" class="gps-batch-hint" style="display: none;">
                            Files with poor GPS may show incorrect speed, position, and map data.
                        </p>
                    </div>
                    <div class="modal-footer gps-batch-footer">
                        <button id="gps-batch-cancel-btn" class="btn btn-secondary">Cancel</button>
                        <button id="gps-batch-skip-btn" class="btn btn-primary" style="display: none;">Skip Poor GPS</button>
                        <button id="gps-batch-render-btn" class="btn btn-primary">Continue</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        this.modal = document.getElementById('gps-batch-warning-modal');
        this.titleEl = document.getElementById('gps-batch-warning-title');
        this.messageEl = document.getElementById('gps-batch-warning-message');
        this.tableBody = document.getElementById('gps-batch-table-body');
        this.hintEl = document.getElementById('gps-batch-hint');
        this.cancelBtn = document.getElementById('gps-batch-cancel-btn');
        this.skipBtn = document.getElementById('gps-batch-skip-btn');
        this.renderBtn = document.getElementById('gps-batch-render-btn');
        window.i18n?.apply(this.modal);
    }

    _attachEventListeners() {
        this.cancelBtn.addEventListener('click', () => this._resolve(null));
        this.skipBtn.addEventListener('click', () => this._resolve('skip'));
        this.renderBtn.addEventListener('click', () => this._resolve('render_all'));

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.style.display === 'flex') {
                this._resolve(null);
            }
        });
    }

    /**
     * Show the GPS quality dialog with table of all files
     * @param {Array} gpsFiles - List of all files with GPS info
     * @param {Object} gpsFiles[].video_path - Path to video file
     * @param {string} gpsFiles[].quality_score - Quality score
     * @param {number|null} gpsFiles[].usable_percentage - Percentage of usable GPS points
     * @param {number|null} gpsFiles[].dop_mean - Average DOP value
     * @param {boolean} gpsFiles[].has_external_gps - True if external GPX provided
     * @param {Object} options - Configuration options
     * @param {number} options.issuesCount - Count of files with GPS issues
     * @returns {Promise<'skip'|'render_all'|null>} User's choice
     */
    show(gpsFiles, options = {}) {
        return new Promise((resolve) => {
            this.resolvePromise = resolve;

            const issuesCount = options.issuesCount || 0;
            const hasIssues = issuesCount > 0;

            // Set title and message based on issues
            if (hasIssues) {
                this.titleEl.textContent = window.i18n?.t('GPS Quality Issues Found') || 'GPS Quality Issues Found';
                this.messageEl.textContent =
                    `${issuesCount} / ${gpsFiles.length} ${window.i18n?.t('files have GPS quality issues:') || 'files have GPS quality issues:'}`;
                this.hintEl.style.display = 'block';
                this.skipBtn.style.display = 'inline-block';
                this.renderBtn.textContent = window.i18n?.t('Render All') || 'Render All';
                this.renderBtn.classList.remove('btn-primary');
                this.renderBtn.classList.add('btn-warning');
            } else {
                this.titleEl.textContent = window.i18n?.t('GPS Quality Check') || 'GPS Quality Check';
                this.messageEl.textContent = `${window.i18n?.t('All files have good GPS quality:') || 'All files have good GPS quality:'} ${gpsFiles.length}`;
                this.hintEl.style.display = 'none';
                this.skipBtn.style.display = 'none';
                this.renderBtn.textContent = window.i18n?.t('Continue') || 'Continue';
                this.renderBtn.classList.remove('btn-warning');
                this.renderBtn.classList.add('btn-primary');
            }

            // Populate table
            this.tableBody.innerHTML = '';
            gpsFiles.forEach(file => {
                const row = document.createElement('tr');
                const isIssue = ['poor', 'no_signal'].includes(file.quality_score);
                if (isIssue) {
                    row.classList.add('gps-row-issue');
                }

                // Extract filename from path
                const filename = file.video_path.split('/').pop();

                // Quality badge
                const qualityBadge = this._formatQualityBadge(file.quality_score, file.has_external_gps);

                // Usable percentage
                const usableStr = file.usable_percentage != null
                    ? `${Math.round(file.usable_percentage)}%`
                    : '-';

                // DOP
                const dopStr = file.dop_mean != null
                    ? file.dop_mean.toFixed(1)
                    : '-';

                row.innerHTML = `
                    <td class="gps-cell-filename" title="${this._escapeHtml(file.video_path)}">${this._escapeHtml(filename)}</td>
                    <td class="gps-cell-quality">${qualityBadge}</td>
                    <td class="gps-cell-usable">${usableStr}</td>
                    <td class="gps-cell-dop">${dopStr}</td>
                `;
                this.tableBody.appendChild(row);
            });

            // Show modal
            this.modal.style.display = 'flex';
            window.i18n?.apply(this.modal);
        });
    }

    _formatQualityBadge(score, hasExternalGps) {
        const labels = {
            'excellent': { text: window.i18n?.t('Excellent') || 'Excellent', class: 'gps-quality-excellent' },
            'good': { text: window.i18n?.t('Good') || 'Good', class: 'gps-quality-good' },
            'ok': { text: 'OK', class: 'gps-quality-ok' },
            'poor': { text: window.i18n?.t('Poor') || 'Poor', class: 'gps-quality-poor' },
            'no_signal': { text: window.i18n?.t('No Signal') || 'No Signal', class: 'gps-quality-no-signal' },
            'skipped': { text: hasExternalGps ? (window.i18n?.t('External GPX') || 'External GPX') : (window.i18n?.t('Skipped') || 'Skipped'), class: 'gps-quality-skipped' },
            'not_found': { text: window.i18n?.t('Not Found') || 'Not Found', class: 'gps-quality-error' },
            'error': { text: window.i18n?.t('Error') || 'Error', class: 'gps-quality-error' },
            'unknown': { text: window.i18n?.t('Unknown') || 'Unknown', class: 'gps-quality-skipped' },
        };

        const info = labels[score] || { text: score, class: 'gps-quality-skipped' };
        return `<span class="gps-quality-badge ${info.class}">${info.text}</span>`;
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    _resolve(value) {
        this.modal.style.display = 'none';
        if (this.resolvePromise) {
            this.resolvePromise(value);
            this.resolvePromise = null;
        }
    }
}

// Export as singleton
window.GPSBatchWarningDialog = GPSBatchWarningDialog;
window.gpsBatchWarningDialog = new GPSBatchWarningDialog();
