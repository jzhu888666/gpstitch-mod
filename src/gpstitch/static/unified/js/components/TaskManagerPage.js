/**
 * TaskManagerPage - unified render task management.
 * Shows single render jobs and batch jobs from the shared render queue.
 */

class TaskManagerPage {
    constructor(state) {
        this.state = state;
        this.jobs = [];
        this.selectedJobId = null;
        this.selectedJobIds = new Set();
        this.logsByJob = new Map();
        this.renderConcurrency = 1;
        this.shutdownAfterAllTasks = false;
        this.shutdownSupported = false;
        this.pollInterval = null;
        this.isOpen = false;
        this._jobsRequestPending = false;
        this._logsRequestPending = false;

        this._createPage();
        this._attachEventListeners();

        window.addEventListener('beforeunload', () => this._stopPolling());
    }

    _createPage() {
        const pageHtml = `
            <div id="task-manager-page" class="modal-overlay task-manager-overlay" style="display: none;">
                <div class="modal task-manager-modal">
                    <div class="modal-header task-manager-header">
                        <div>
                            <h3>Task Manager</h3>
                            <div class="task-manager-subtitle">All render jobs share one managed queue</div>
                        </div>
                        <button class="modal-close" id="task-manager-close">&times;</button>
                    </div>
                    <div class="modal-body task-manager-body">
                        <div class="task-manager-toolbar">
                            <div class="task-manager-controls">
                                <label class="task-shutdown-control checkbox-label">
                                    <input type="checkbox" id="task-shutdown-after-all">
                                    <span>Shutdown when all tasks finish</span>
                                </label>
                                <label class="task-concurrency-control">
                                    <span>Concurrency</span>
                                    <select id="task-concurrency-select">
                                        <option value="1">1</option>
                                        <option value="2">2</option>
                                        <option value="3">3</option>
                                    </select>
                                </label>
                                <button id="task-clear-finished" class="btn btn-secondary" disabled>Clear Finished</button>
                                <button id="task-retry-selected" class="btn btn-secondary" disabled>Retry Failed</button>
                                <button id="task-cancel-selected" class="btn btn-secondary" disabled>Cancel Selected</button>
                                <button id="task-refresh" class="btn btn-secondary">Refresh</button>
                            </div>
                        </div>

                        <div id="task-summary" class="task-summary-grid"></div>

                        <div class="task-manager-content">
                            <section class="task-list-panel">
                                <div class="task-section-header">
                                    <label class="task-select-all-control" title="Select all tasks">
                                        <input type="checkbox" id="task-select-all">
                                        <span>Tasks</span>
                                    </label>
                                    <span id="task-count" class="task-count">0</span>
                                </div>
                                <div id="task-list" class="task-list"></div>
                            </section>
                            <aside class="task-detail-panel">
                                <div class="task-section-header">
                                    <span>Details</span>
                                    <span id="task-selected-id" class="task-id-muted">-</span>
                                </div>
                                <div id="task-detail" class="task-detail"></div>
                            </aside>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button id="task-manager-footer-close" class="btn btn-secondary">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', pageHtml);
        this.modal = document.getElementById('task-manager-page');
        this.closeBtn = document.getElementById('task-manager-close');
        this.footerCloseBtn = document.getElementById('task-manager-footer-close');
        this.refreshBtn = document.getElementById('task-refresh');
        this.clearFinishedBtn = document.getElementById('task-clear-finished');
        this.retrySelectedBtn = document.getElementById('task-retry-selected');
        this.cancelSelectedBtn = document.getElementById('task-cancel-selected');
        this.selectAllCheckbox = document.getElementById('task-select-all');
        this.concurrencySelect = document.getElementById('task-concurrency-select');
        this.shutdownAfterAllTasksCheckbox = document.getElementById('task-shutdown-after-all');
        this.summaryEl = document.getElementById('task-summary');
        this.taskCountEl = document.getElementById('task-count');
        this.listEl = document.getElementById('task-list');
        this.detailEl = document.getElementById('task-detail');
        this.selectedIdEl = document.getElementById('task-selected-id');
        window.i18n?.apply(this.modal);
    }

    _attachEventListeners() {
        this.closeBtn.addEventListener('click', () => this.close());
        this.footerCloseBtn.addEventListener('click', () => this.close());

        this.modal.addEventListener('click', (event) => {
            if (event.target === this.modal) {
                this.close();
            }
        });

        this.refreshBtn.addEventListener('click', () => this._refresh(true));
        this.clearFinishedBtn.addEventListener('click', () => this._clearFinishedJobs());
        this.retrySelectedBtn.addEventListener('click', () => this._retrySelectedFailedJobs());
        this.cancelSelectedBtn.addEventListener('click', () => this._cancelSelectedJobs());
        this.selectAllCheckbox.addEventListener('change', () => this._toggleSelectAll());
        this.concurrencySelect.addEventListener('change', () => this._updateConcurrency());
        this.shutdownAfterAllTasksCheckbox.addEventListener('change', () => this._updateShutdownAfterAllTasks());

        this.listEl.addEventListener('click', (event) => {
            if (event.target.closest('[data-select-job]')) {
                event.stopPropagation();
                return;
            }

            const cancelJobBtn = event.target.closest('[data-cancel-job]');
            if (cancelJobBtn) {
                event.preventDefault();
                event.stopPropagation();
                this._cancelJob(cancelJobBtn.dataset.cancelJob);
                return;
            }

            const row = event.target.closest('[data-job-id]');
            if (row) {
                this._selectJob(row.dataset.jobId);
            }
        });

        this.listEl.addEventListener('change', (event) => {
            const selectInput = event.target.closest('[data-select-job]');
            if (!selectInput) return;

            if (selectInput.checked) {
                this.selectedJobIds.add(selectInput.dataset.selectJob);
            } else {
                this.selectedJobIds.delete(selectInput.dataset.selectJob);
            }
            this._render();
        });

        this.detailEl.addEventListener('click', (event) => {
            if (event.target.closest('[data-refresh-logs]')) {
                this._refreshLogs(true);
            }
        });

        this.state.on('language:changed', () => {
            this._render();
            window.i18n?.apply(this.modal);
        });

        document.addEventListener('render-queue:changed', () => this.notifyQueueChanged());
    }

    open() {
        this.isOpen = true;
        this.modal.style.display = 'flex';
        this._refresh();
        this._startPolling();
    }

    close() {
        this.isOpen = false;
        this.modal.style.display = 'none';
        this._stopPolling();
    }

    notifyQueueChanged() {
        if (!this.isOpen) return;
        this._refresh();
    }

    _startPolling() {
        this._stopPolling();
        this.pollInterval = setInterval(() => this._refresh(), 2000);
    }

    _stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async _refresh(showToast = false) {
        if (!this.isOpen || this._jobsRequestPending) return;

        this._jobsRequestPending = true;
        try {
            const response = await fetch('/api/render/jobs?limit=100');
            if (!response.ok) {
                throw new Error(this._t('Failed to load tasks'));
            }

            const data = await response.json();
            this.jobs = data.jobs || [];
            this._pruneSelectedJobs();
            this.renderConcurrency = data.render_concurrency || 1;
            this.shutdownAfterAllTasks = !!data.shutdown_after_all_tasks;
            this.shutdownSupported = !!data.shutdown_supported;
            if (this.concurrencySelect && this.concurrencySelect.value !== String(this.renderConcurrency)) {
                this.concurrencySelect.value = String(this.renderConcurrency);
            }
            if (this.shutdownAfterAllTasksCheckbox) {
                this.shutdownAfterAllTasksCheckbox.checked = this.shutdownAfterAllTasks;
                this.shutdownAfterAllTasksCheckbox.disabled = !this.shutdownSupported;
                this.shutdownAfterAllTasksCheckbox.title = this.shutdownSupported
                    ? this._t('Shutdown after all tasks finish')
                    : this._t('Shutdown is only supported on Windows');
            }

            if (!this.selectedJobId || !this.jobs.some(job => job.job_id === this.selectedJobId)) {
                this.selectedJobId = this.jobs[0]?.job_id || null;
            }

            this._render();
            await this._refreshLogs(true);

            if (showToast) {
                window.toast?.success(this._t('Tasks refreshed'), { title: this._t('Task Manager'), duration: 2000 });
            }
        } catch (error) {
            console.error('Failed to refresh tasks:', error);
            if (showToast) {
                window.toast?.error(error.message, { title: this._t('Task Manager') });
            }
        } finally {
            this._jobsRequestPending = false;
        }
    }

    _render() {
        if (!this.summaryEl || !this.listEl || !this.detailEl) return;
        this._renderSummary();
        this._renderTaskList();
        this._renderDetail();
        this._updateBulkActionState();
        this._updateSelectAllState();
        window.i18n?.apply(this.modal);
    }

    _renderSummary() {
        const counts = this._countJobs(this.jobs);
        const summaryItems = [
            ['Pending', counts.pending],
            ['Running', counts.running],
            ['Completed', counts.completed],
            ['Failed', counts.failed],
            ['Cancelled', counts.cancelled],
        ];

        this.summaryEl.innerHTML = summaryItems.map(([label, value]) => `
            <div class="task-summary-item task-summary-${label.toLowerCase()}">
                <span class="task-summary-value">${value}</span>
                <span class="task-summary-label">${this._escapeHtml(this._t(label))}</span>
            </div>
        `).join('');

        if (this.clearFinishedBtn) {
            const removableCount = counts.completed + counts.failed + counts.cancelled;
            this.clearFinishedBtn.disabled = removableCount === 0;
            this.clearFinishedBtn.title = removableCount > 0
                ? `${this._t('Remove finished tasks')} (${removableCount})`
                : this._t('No finished tasks to remove');
        }
    }

    _updateBulkActionState() {
        const failedSelected = this._getSelectedFailedJobs();
        const cancellableSelected = this._getSelectedCancellableJobs();

        if (this.retrySelectedBtn) {
            this.retrySelectedBtn.disabled = failedSelected.length === 0;
            this.retrySelectedBtn.textContent = failedSelected.length > 0
                ? `${this._t('Retry Failed')} (${failedSelected.length})`
                : this._t('Retry Failed');
            this.retrySelectedBtn.title = failedSelected.length > 0
                ? this._t('Retry selected failed tasks')
                : this._t('Select failed tasks to retry');
        }

        if (this.cancelSelectedBtn) {
            this.cancelSelectedBtn.disabled = cancellableSelected.length === 0;
            this.cancelSelectedBtn.textContent = cancellableSelected.length > 0
                ? `${this._t('Cancel Selected')} (${cancellableSelected.length})`
                : this._t('Cancel Selected');
            this.cancelSelectedBtn.title = cancellableSelected.length > 0
                ? this._t('Cancel selected queued or running tasks')
                : this._t('Select queued or running tasks to cancel');
        }
    }

    _renderTaskList() {
        this.taskCountEl.textContent = String(this.jobs.length);

        if (this.jobs.length === 0) {
            this.listEl.innerHTML = `
                <div class="task-empty">
                    <div class="task-empty-title">${this._escapeHtml(this._t('No render tasks yet'))}</div>
                    <div class="task-empty-text">${this._escapeHtml(this._t('Start a render or batch render to see it here.'))}</div>
                </div>
            `;
            return;
        }

        this.listEl.innerHTML = this.jobs.map(job => this._renderRow(job)).join('');
    }

    _renderRow(job) {
        const progress = Math.round(job.progress?.percent || 0);
        const selected = job.job_id === this.selectedJobId ? 'active' : '';
        const bulkSelected = this.selectedJobIds.has(job.job_id) ? 'bulk-selected' : '';
        const statusClass = `task-status-${job.status || 'unknown'}`;
        const outputName = this._basename(job.output_file);
        const metaParts = [
            this._formatDate(job.created_at),
            outputName,
        ].filter(Boolean);

        return `
            <div class="task-row ${selected} ${bulkSelected}" data-job-id="${this._escapeHtml(job.job_id)}">
                <label class="task-row-select-cell" title="${this._escapeHtml(this._t('Select task'))}">
                    <input
                        type="checkbox"
                        class="task-row-select"
                        data-select-job="${this._escapeHtml(job.job_id)}"
                        ${this.selectedJobIds.has(job.job_id) ? 'checked' : ''}
                    >
                </label>
                <div class="task-row-main">
                    <div class="task-row-title">${this._escapeHtml(job.video_name || this._t('Unknown'))}</div>
                    <div class="task-row-meta">${this._escapeHtml(metaParts.join(' - '))}</div>
                </div>
                <div class="task-row-progress">
                    <div class="task-progress-mini">
                        <div class="task-progress-mini-fill" style="width: ${progress}%"></div>
                    </div>
                    <span>${progress}%</span>
                </div>
                <span class="task-status-badge ${statusClass}">${this._escapeHtml(this._formatStatus(job.status))}</span>
                ${job.can_cancel ? `
                    <button
                        class="btn btn-sm btn-secondary task-row-cancel"
                        data-cancel-job="${this._escapeHtml(job.job_id)}"
                    >${this._escapeHtml(this._t('Cancel'))}</button>
                ` : `<span class="task-row-terminal">-</span>`}
            </div>
        `;
    }

    _renderDetail() {
        const job = this.jobs.find(item => item.job_id === this.selectedJobId);
        if (!job) {
            this.selectedIdEl.textContent = '-';
            this.detailEl.innerHTML = `
                <div class="task-empty">
                    <div class="task-empty-title">${this._escapeHtml(this._t('Select a task'))}</div>
                    <div class="task-empty-text">${this._escapeHtml(this._t('Task logs and render details will appear here.'))}</div>
                </div>
            `;
            return;
        }

        this.selectedIdEl.textContent = this._shortId(job.job_id);
        const logs = this.logsByJob.get(job.job_id) || [];
        const progress = job.progress || {};
        const detailRows = [
            ['Status', this._formatStatus(job.status)],
            ['Source', job.source_file || job.video_name || '-'],
            ['Output', job.output_file || '-'],
            ['Created', this._formatDate(job.created_at)],
            ['Started', this._formatDate(job.started_at)],
            ['Completed', this._formatDate(job.completed_at)],
            ['Frame', this._formatFrames(progress)],
            ['Speed', progress.fps ? `${progress.fps.toFixed(1)} frames/s` : '-'],
            ['ETA', this._formatEta(progress.eta_seconds)],
            ['Retry', `${job.retry_count || 0} / ${job.max_retries ?? 3}`],
        ];

        this.detailEl.innerHTML = `
            <div class="task-detail-summary">
                ${detailRows.map(([label, value]) => `
                    <div class="task-detail-row">
                        <span>${this._escapeHtml(this._t(label))}</span>
                        <strong title="${this._escapeHtml(value)}">${this._escapeHtml(value)}</strong>
                    </div>
                `).join('')}
            </div>
            ${job.error ? `<div class="task-error">${this._escapeHtml(job.error)}</div>` : ''}
            <div class="task-log-panel">
                <div class="task-section-header">
                    <span>${this._escapeHtml(this._t('Log Output'))}</span>
                    <button class="btn-link" type="button" data-refresh-logs>${this._escapeHtml(this._t('Refresh'))}</button>
                </div>
                <pre id="task-log-content" class="task-log-content">${this._escapeHtml(logs.join('\n'))}</pre>
            </div>
        `;

        const logContent = document.getElementById('task-log-content');
        if (logContent) {
            logContent.scrollTop = logContent.scrollHeight;
        }
    }

    async _selectJob(jobId) {
        if (!jobId || jobId === this.selectedJobId) return;
        this.selectedJobId = jobId;
        this._render();
        await this._refreshLogs(true);
    }

    async _refreshLogs(force = false) {
        if (!this.isOpen || !this.selectedJobId || this._logsRequestPending) return;
        if (!force && this.logsByJob.has(this.selectedJobId)) return;

        this._logsRequestPending = true;
        const jobId = this.selectedJobId;
        try {
            const response = await fetch(`/api/render/logs/${jobId}?tail=200`);
            if (!response.ok) return;

            const data = await response.json();
            this.logsByJob.set(jobId, data.log_lines || []);
            if (this.selectedJobId === jobId) {
                this._renderDetail();
            }
        } catch (error) {
            console.error('Failed to load task logs:', error);
        } finally {
            this._logsRequestPending = false;
        }
    }

    async _cancelJob(jobId) {
        const job = this.jobs.find(item => item.job_id === jobId);
        if (!job || !job.can_cancel) return;

        if (!confirm(this._t('Cancel this render task?'))) {
            return;
        }

        try {
            const response = await fetch(`/api/render/cancel/${jobId}`, { method: 'POST' });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || this._t('Failed to cancel render'));
            }
            window.toast?.success(this._t('Task cancelled'), { title: this._t('Task Manager'), duration: 3000 });
            this.selectedJobIds.delete(jobId);
            await this._refresh();
        } catch (error) {
            console.error('Failed to cancel task:', error);
            window.toast?.error(error.message, { title: this._t('Task Manager') });
        }
    }

    async _retrySelectedFailedJobs() {
        const jobs = this._getSelectedFailedJobs();
        if (jobs.length === 0) return;

        const message = `${this._t('Retry selected failed tasks?')}\n${jobs.length} ${this._t('tasks')}`;
        if (!confirm(message)) {
            return;
        }

        try {
            const response = await fetch('/api/render/jobs/retry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_ids: jobs.map(job => job.job_id) }),
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || this._t('Failed to retry tasks'));
            }

            const data = await response.json();
            for (const job of jobs) {
                this.selectedJobIds.delete(job.job_id);
            }

            window.toast?.success(
                `${data.affected || 0} ${this._t('tasks retried')}`,
                { title: this._t('Task Manager'), duration: 3000 }
            );
            await this._refresh();
        } catch (error) {
            console.error('Failed to retry selected tasks:', error);
            window.toast?.error(error.message, { title: this._t('Task Manager') });
        }
    }

    async _cancelSelectedJobs() {
        const jobs = this._getSelectedCancellableJobs();
        if (jobs.length === 0) return;

        const message = `${this._t('Cancel selected queued or running tasks?')}\n${jobs.length} ${this._t('tasks')}`;
        if (!confirm(message)) {
            return;
        }

        try {
            const response = await fetch('/api/render/jobs/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_ids: jobs.map(job => job.job_id) }),
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || this._t('Failed to cancel selected tasks'));
            }

            const data = await response.json();
            for (const job of jobs) {
                this.selectedJobIds.delete(job.job_id);
            }

            window.toast?.success(
                `${data.affected || 0} ${this._t('tasks cancelled')}`,
                { title: this._t('Task Manager'), duration: 3000 }
            );
            await this._refresh();
        } catch (error) {
            console.error('Failed to cancel selected tasks:', error);
            window.toast?.error(error.message, { title: this._t('Task Manager') });
        }
    }

    async _clearFinishedJobs() {
        const removableStatuses = new Set(['completed', 'failed', 'cancelled']);
        const removableJobs = this.jobs.filter(job => removableStatuses.has(job.status));
        if (removableJobs.length === 0) {
            return;
        }

        const message = `${this._t('Remove completed, failed, and cancelled tasks from Task Manager?')}\n${removableJobs.length} ${this._t('tasks')}`;
        if (!confirm(message)) {
            return;
        }

        try {
            const response = await fetch('/api/render/jobs/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ statuses: Array.from(removableStatuses) }),
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || this._t('Failed to remove tasks'));
            }

            const data = await response.json();
            for (const job of removableJobs) {
                this.logsByJob.delete(job.job_id);
                this.selectedJobIds.delete(job.job_id);
            }

            const selectedJob = this.jobs.find(job => job.job_id === this.selectedJobId);
            if (selectedJob && removableStatuses.has(selectedJob.status)) {
                this.selectedJobId = null;
            }

            window.toast?.success(
                `${data.removed || 0} ${this._t('tasks removed')}`,
                { title: this._t('Task Manager'), duration: 2500 }
            );
            await this._refresh();
        } catch (error) {
            console.error('Failed to clear finished tasks:', error);
            window.toast?.error(error.message, { title: this._t('Task Manager') });
        }
    }

    _countJobs(jobs) {
        return jobs.reduce((counts, job) => {
            counts[job.status] = (counts[job.status] || 0) + 1;
            return counts;
        }, { pending: 0, running: 0, completed: 0, failed: 0, cancelled: 0 });
    }

    _getSelectedJobs() {
        return this.jobs.filter(job => this.selectedJobIds.has(job.job_id));
    }

    _getSelectedFailedJobs() {
        return this._getSelectedJobs().filter(job => job.status === 'failed');
    }

    _getSelectedCancellableJobs() {
        return this._getSelectedJobs().filter(job => job.can_cancel || ['pending', 'running'].includes(job.status));
    }

    _pruneSelectedJobs() {
        const validJobIds = new Set(this.jobs.map(job => job.job_id));
        for (const jobId of Array.from(this.selectedJobIds)) {
            if (!validJobIds.has(jobId)) {
                this.selectedJobIds.delete(jobId);
            }
        }
    }

    _toggleSelectAll() {
        if (!this.selectAllCheckbox) return;

        if (this.selectAllCheckbox.checked) {
            for (const job of this.jobs) {
                this.selectedJobIds.add(job.job_id);
            }
        } else {
            for (const job of this.jobs) {
                this.selectedJobIds.delete(job.job_id);
            }
        }
        this._render();
    }

    _updateSelectAllState() {
        if (!this.selectAllCheckbox) return;

        const total = this.jobs.length;
        const selected = this.jobs.filter(job => this.selectedJobIds.has(job.job_id)).length;
        this.selectAllCheckbox.disabled = total === 0;
        this.selectAllCheckbox.checked = total > 0 && selected === total;
        this.selectAllCheckbox.indeterminate = selected > 0 && selected < total;
        this.selectAllCheckbox.title = total > 0
            ? this._t('Select all tasks')
            : this._t('No render tasks yet');
    }

    async _updateConcurrency() {
        const concurrency = parseInt(this.concurrencySelect.value, 10) || 1;
        try {
            const response = await fetch('/api/render/concurrency', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ concurrency })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || this._t('Failed to update concurrency'));
            }
            const data = await response.json();
            this.renderConcurrency = data.concurrency || concurrency;
            this.concurrencySelect.value = String(this.renderConcurrency);
            window.toast?.success(
                `${this._t('Render concurrency')}: ${this.renderConcurrency}`,
                { title: this._t('Task Manager'), duration: 2500 }
            );
            await this._refresh();
        } catch (error) {
            console.error('Failed to update render concurrency:', error);
            window.toast?.error(error.message, { title: this._t('Task Manager') });
            this.concurrencySelect.value = String(this.renderConcurrency);
        }
    }

    async _updateShutdownAfterAllTasks() {
        const enabled = !!this.shutdownAfterAllTasksCheckbox.checked;
        try {
            const response = await fetch('/api/render/task-shutdown', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || this._t('Failed to update shutdown setting'));
            }
            const data = await response.json();
            this.shutdownAfterAllTasks = !!data.enabled;
            this.shutdownSupported = !!data.supported;
            this.shutdownAfterAllTasksCheckbox.checked = this.shutdownAfterAllTasks;
            this.shutdownAfterAllTasksCheckbox.disabled = !this.shutdownSupported;
            window.toast?.success(
                `${this._t('Shutdown when all tasks finish')}: ${this.shutdownAfterAllTasks ? this._t('Enabled') : this._t('Disabled')}`,
                { title: this._t('Task Manager'), duration: 2500 }
            );
        } catch (error) {
            console.error('Failed to update task shutdown setting:', error);
            window.toast?.error(error.message, { title: this._t('Task Manager') });
            this.shutdownAfterAllTasksCheckbox.checked = this.shutdownAfterAllTasks;
        }
    }

    _formatFrames(progress) {
        if (!progress?.current_frame) return '-';
        return progress.total_frames
            ? `${progress.current_frame} / ${progress.total_frames}`
            : `${progress.current_frame}`;
    }

    _formatEta(seconds) {
        if (!seconds || seconds <= 0) return '-';
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
        if (mins > 0) return `${mins}m ${secs}s`;
        return `${secs}s`;
    }

    _formatStatus(status) {
        const statusMap = {
            pending: 'Pending',
            running: 'Running',
            completed: 'Completed',
            failed: 'Failed',
            cancelled: 'Cancelled',
        };
        return this._t(statusMap[status] || status || 'Unknown');
    }

    _formatDate(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '-';
        return date.toLocaleString();
    }

    _basename(path) {
        if (!path) return '';
        const normalized = path.replace(/\\/g, '/');
        return normalized.substring(normalized.lastIndexOf('/') + 1);
    }

    _shortId(id) {
        if (!id) return '-';
        return id.length > 8 ? id.substring(0, 8) : id;
    }

    _t(text) {
        return window.i18n?.t(text) || text;
    }

    _escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = String(value ?? '');
        return div.innerHTML;
    }
}

window.TaskManagerPage = TaskManagerPage;
window.taskManagerPage = null;
