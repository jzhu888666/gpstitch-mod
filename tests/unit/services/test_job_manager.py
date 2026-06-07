"""Unit tests for JobManager service."""

from datetime import UTC, datetime, timedelta

from gpstitch.models.job import JobStatus
from gpstitch.models.schemas import FileInfo, FileRole


class TestJobManagerCreate:
    """Tests for job creation."""

    async def test_create_job_generates_id(self, clean_job_manager, sample_job_config):
        """Created job should have a UUID."""
        job = await clean_job_manager.create_job(sample_job_config)

        assert job.id
        assert len(job.id) == 36

    async def test_create_job_status_pending(self, clean_job_manager, sample_job_config):
        """New job should have PENDING status."""
        job = await clean_job_manager.create_job(sample_job_config)

        assert job.status == JobStatus.PENDING

    async def test_create_job_persisted(self, clean_job_manager, sample_job_config):
        """Job should be persisted to disk."""
        job = await clean_job_manager.create_job(sample_job_config)
        job_file = clean_job_manager._job_file_path(job.id)

        assert job_file.exists()

    async def test_create_job_stores_config(self, clean_job_manager, sample_job_config):
        """Job should store configuration."""
        job = await clean_job_manager.create_job(sample_job_config)

        assert job.config.layout == sample_job_config.layout
        assert job.config.output_file == sample_job_config.output_file

    async def test_create_job_snapshots_session_files(self, clean_job_manager, sample_job_config, monkeypatch):
        """Jobs persist session files so local-mode retries survive server restart."""
        file_info = FileInfo(
            filename="video.mp4",
            file_path="H:/video.mp4",
            file_type="video",
            role=FileRole.PRIMARY,
        )

        class FakeFileManager:
            def get_files(self, session_id):
                return [file_info] if session_id == sample_job_config.session_id else []

        monkeypatch.setattr("gpstitch.services.file_manager.file_manager", FakeFileManager())

        job = await clean_job_manager.create_job(sample_job_config)

        assert job.session_files == [file_info]

    async def test_create_job_with_batch(self, clean_job_manager, sample_job_config):
        """Create job with batch ID."""
        batch_id = "batch-123"

        job = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)

        assert job.batch_id == batch_id


class TestJobManagerQuery:
    """Tests for job queries."""

    async def test_get_job(self, clean_job_manager, sample_job_config):
        """Get job by ID."""
        job = await clean_job_manager.create_job(sample_job_config)

        retrieved = await clean_job_manager.get_job(job.id)

        assert retrieved is not None
        assert retrieved.id == job.id

    async def test_get_job_nonexistent(self, clean_job_manager):
        """Get nonexistent job returns None."""
        result = await clean_job_manager.get_job("nonexistent")

        assert result is None

    async def test_list_jobs(self, clean_job_manager, sample_job_config):
        """List jobs returns all jobs."""
        job1 = await clean_job_manager.create_job(sample_job_config)
        job2 = await clean_job_manager.create_job(sample_job_config)

        jobs = await clean_job_manager.list_jobs()

        assert len(jobs) >= 2
        job_ids = [j.id for j in jobs]
        assert job1.id in job_ids
        assert job2.id in job_ids

    async def test_list_jobs_newest_first(self, clean_job_manager, sample_job_config):
        """List jobs should return newest first."""
        await clean_job_manager.create_job(sample_job_config)
        job2 = await clean_job_manager.create_job(sample_job_config)

        jobs = await clean_job_manager.list_jobs()

        # job2 created after job1, should be first
        assert jobs[0].id == job2.id

    async def test_get_next_pending_job_fifo(self, clean_job_manager, sample_job_config):
        """Get next pending job in FIFO order."""
        job1 = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.create_job(sample_job_config)

        next_job = await clean_job_manager.get_next_pending_job()

        assert next_job.id == job1.id  # First created

    async def test_has_pending_jobs(self, clean_job_manager, sample_job_config):
        """Check if there are pending jobs."""
        assert not await clean_job_manager.has_pending_jobs()

        await clean_job_manager.create_job(sample_job_config)

        assert await clean_job_manager.has_pending_jobs()

    async def test_has_active_job(self, clean_job_manager, sample_job_config):
        """Check if there's an active job."""
        assert not await clean_job_manager.has_active_job()

        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        assert await clean_job_manager.has_active_job()

    async def test_get_current_job(self, clean_job_manager, sample_job_config):
        """Get currently running job."""
        job = await clean_job_manager.create_job(sample_job_config)

        # No current job initially
        assert await clean_job_manager.get_current_job() is None

        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        current = await clean_job_manager.get_current_job()
        assert current is not None
        assert current.id == job.id

    async def test_get_running_jobs_returns_all_running(self, clean_job_manager, sample_job_config):
        """Multiple running jobs can be tracked at once."""
        job1 = await clean_job_manager.create_job(sample_job_config)
        job2 = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job1.id, JobStatus.RUNNING)
        await clean_job_manager.update_job_status(job2.id, JobStatus.RUNNING)

        running = await clean_job_manager.get_running_jobs()

        assert [job.id for job in running] == [job1.id, job2.id]
        assert await clean_job_manager.active_job_count() == 2

    async def test_get_next_pending_jobs_fifo(self, clean_job_manager, sample_job_config):
        """Get multiple pending jobs in FIFO order."""
        job1 = await clean_job_manager.create_job(sample_job_config)
        job2 = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.create_job(sample_job_config)

        pending = await clean_job_manager.get_next_pending_jobs(2)

        assert [job.id for job in pending] == [job1.id, job2.id]


class TestJobManagerUpdate:
    """Tests for job updates."""

    async def test_update_job_status_to_running(self, clean_job_manager, sample_job_config):
        """Update job status to RUNNING sets started_at."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.RUNNING
        assert updated.started_at is not None

    async def test_update_job_status_to_completed(self, clean_job_manager, sample_job_config):
        """Update job status to COMPLETED sets completed_at."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        await clean_job_manager.update_job_status(job.id, JobStatus.COMPLETED)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_update_job_status_with_error(self, clean_job_manager, sample_job_config):
        """Update job status with error message."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_status(job.id, JobStatus.FAILED, error="Test error")

        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.FAILED
        assert updated.error == "Test error"

    async def test_update_job_progress(self, clean_job_manager, sample_job_config):
        """Update job progress."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_progress(
            job.id,
            percent=50.0,
            current_frame=500,
            total_frames=1000,
            fps=30.0,
            eta_seconds=16.7,
        )

        updated = await clean_job_manager.get_job(job.id)
        assert updated.progress.percent == 50.0
        assert updated.progress.current_frame == 500
        assert updated.progress.total_frames == 1000
        assert updated.progress.fps == 30.0
        assert updated.progress.eta_seconds == 16.7

    async def test_update_job_progress_capped_at_100(self, clean_job_manager, sample_job_config):
        """Progress should be capped at 100%."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_progress(job.id, percent=150.0)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.progress.percent == 100.0

    async def test_append_job_log(self, clean_job_manager, sample_job_config):
        """Append log lines to job."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.append_job_log(job.id, "Line 1")
        await clean_job_manager.append_job_log(job.id, "Line 2")

        updated = await clean_job_manager.get_job(job.id)
        assert "Line 1" in updated.log_lines
        assert "Line 2" in updated.log_lines

    async def test_append_job_log_truncates_at_500(self, clean_job_manager, sample_job_config):
        """Log should be truncated to 500 lines max."""
        job = await clean_job_manager.create_job(sample_job_config)

        # Add 600 lines
        for i in range(600):
            await clean_job_manager.append_job_log(job.id, f"Line {i}")

        updated = await clean_job_manager.get_job(job.id)
        assert len(updated.log_lines) == 500
        assert "Line 599" in updated.log_lines  # Latest should be kept

    async def test_set_job_pid(self, clean_job_manager, sample_job_config):
        """Set process ID for job."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.set_job_pid(job.id, 12345)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.pid == 12345

    async def test_reset_job_for_retry_requeues_running_job(self, clean_job_manager, sample_job_config):
        """A failed attempt should be reset to pending while retry budget remains."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)
        await clean_job_manager.update_job_progress(job.id, 73.0, current_frame=730, total_frames=1000)
        await clean_job_manager.set_job_pid(job.id, 12345)

        retried = await clean_job_manager.reset_job_for_retry(job.id, "temporary render failure")

        assert retried is True
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.PENDING
        assert updated.retry_count == 1
        assert updated.max_retries == 3
        assert updated.started_at is None
        assert updated.completed_at is None
        assert updated.pid is None
        assert updated.error is None
        assert updated.progress.percent == 0
        assert updated.progress.current_frame is None
        assert not await clean_job_manager.has_active_job()
        assert any("Retry 1/3" in line for line in updated.log_lines)
        assert any("temporary render failure" in line for line in updated.log_lines)

    async def test_reset_job_for_retry_stops_at_retry_limit(self, clean_job_manager, sample_job_config):
        """Retry reset should return false once the configured budget is exhausted."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)
        job = await clean_job_manager.get_job(job.id)
        job.retry_count = job.max_retries
        clean_job_manager._persist_job(job)

        retried = await clean_job_manager.reset_job_for_retry(job.id, "still failing")

        assert retried is False
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.RUNNING
        assert updated.retry_count == updated.max_retries

    async def test_retry_failed_job_requeues_manual_retry(self, clean_job_manager, sample_job_config):
        """Manual retry should requeue a failed job with a fresh automatic retry budget."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.FAILED, error="render failed")
        await clean_job_manager.update_job_progress(job.id, 91.0, current_frame=910, total_frames=1000)
        job = await clean_job_manager.get_job(job.id)
        job.retry_count = job.max_retries
        clean_job_manager._persist_job(job)

        retried = await clean_job_manager.retry_failed_job(job.id)

        assert retried is True
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.PENDING
        assert updated.retry_count == 0
        assert updated.started_at is None
        assert updated.completed_at is None
        assert updated.error is None
        assert updated.progress.percent == 0
        assert updated.progress.current_frame is None
        assert any("Manual retry" in line for line in updated.log_lines)

    async def test_retry_failed_job_rejects_non_failed_job(self, clean_job_manager, sample_job_config):
        """Manual retry should not requeue queued or running jobs."""
        job = await clean_job_manager.create_job(sample_job_config)

        retried = await clean_job_manager.retry_failed_job(job.id)

        assert retried is False
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.PENDING


class TestJobManagerBatch:
    """Tests for batch job operations."""

    async def test_count_batch_jobs(self, clean_job_manager, sample_job_config):
        """Count jobs in a batch."""
        batch_id = "batch-test"

        await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        await clean_job_manager.create_job(sample_job_config)  # Different batch

        counts = await clean_job_manager.count_batch_jobs(batch_id)

        assert counts["total"] == 2
        assert counts["pending"] == 2
        assert counts["running"] == 0
        assert counts["completed"] == 0

    async def test_cancel_batch_pending_jobs(self, clean_job_manager, sample_job_config):
        """Cancel all pending jobs in batch."""
        batch_id = "batch-cancel"

        job1 = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        job2 = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)

        cancelled = await clean_job_manager.cancel_batch_pending_jobs(batch_id)

        assert cancelled == 2

        job1_updated = await clean_job_manager.get_job(job1.id)
        job2_updated = await clean_job_manager.get_job(job2.id)

        assert job1_updated.status == JobStatus.CANCELLED
        assert job2_updated.status == JobStatus.CANCELLED

    async def test_get_running_batch_job(self, clean_job_manager, sample_job_config):
        """Get running job in batch."""
        batch_id = "batch-running"

        job = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        running = await clean_job_manager.get_running_batch_job(batch_id)

        assert running is not None
        assert running.id == job.id


class TestJobManagerCleanup:
    """Tests for cleanup operations."""

    async def test_cleanup_old_jobs(self, clean_job_manager, sample_job_config):
        """Cleanup old completed jobs."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.COMPLETED)

        # Manually set completed_at to old date
        updated_job = await clean_job_manager.get_job(job.id)
        updated_job.completed_at = datetime.now(UTC) - timedelta(hours=48)
        clean_job_manager._persist_job(updated_job)

        cleaned = await clean_job_manager.cleanup_old_jobs(max_age_hours=24)

        assert cleaned == 1
        assert await clean_job_manager.get_job(job.id) is None

    async def test_cleanup_old_jobs_keeps_fresh(self, clean_job_manager, sample_job_config):
        """Fresh completed jobs are not cleaned."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.COMPLETED)

        cleaned = await clean_job_manager.cleanup_old_jobs(max_age_hours=24)

        assert cleaned == 0
        assert await clean_job_manager.get_job(job.id) is not None

    async def test_remove_jobs_by_status_removes_terminal_jobs_only(self, clean_job_manager, sample_job_config):
        """Remove selected finished jobs without touching queued or running jobs."""
        completed = await clean_job_manager.create_job(sample_job_config)
        failed = await clean_job_manager.create_job(sample_job_config)
        cancelled = await clean_job_manager.create_job(sample_job_config)
        pending = await clean_job_manager.create_job(sample_job_config)
        running = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_status(completed.id, JobStatus.COMPLETED)
        await clean_job_manager.update_job_status(failed.id, JobStatus.FAILED, error="failed")
        await clean_job_manager.update_job_status(cancelled.id, JobStatus.CANCELLED)
        await clean_job_manager.update_job_status(running.id, JobStatus.RUNNING)

        terminal_files = [
            clean_job_manager._job_file_path(completed.id),
            clean_job_manager._job_file_path(failed.id),
            clean_job_manager._job_file_path(cancelled.id),
        ]
        assert all(path.exists() for path in terminal_files)

        removed = await clean_job_manager.remove_jobs_by_status(
            {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
        )

        assert removed == 3
        assert await clean_job_manager.get_job(completed.id) is None
        assert await clean_job_manager.get_job(failed.id) is None
        assert await clean_job_manager.get_job(cancelled.id) is None
        assert await clean_job_manager.get_job(pending.id) is not None
        assert await clean_job_manager.get_job(running.id) is not None
        assert not any(path.exists() for path in terminal_files)

    async def test_cleanup_orphaned_pending_jobs(self, clean_job_manager, sample_job_config):
        """Cleanup pending jobs with nonexistent sessions."""
        job = await clean_job_manager.create_job(sample_job_config)

        # Valid sessions don't include job's session
        valid_sessions = {"other-session-1", "other-session-2"}

        cleaned = await clean_job_manager.cleanup_orphaned_pending_jobs(valid_sessions)

        assert cleaned == 1
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.FAILED
        assert "orphaned" in updated.error.lower()

    async def test_cleanup_orphaned_pending_jobs_keeps_restorable_local_jobs(
        self, clean_job_manager, sample_job_config, temp_dir
    ):
        """Queued retry jobs with saved local files should not be orphan-cleaned."""
        video_path = temp_dir / "video.mp4"
        video_path.write_bytes(b"fake video")
        config = sample_job_config.model_copy(update={"session_id": "local:lost-session"})
        job = await clean_job_manager.create_job(config)
        job.session_files = [
            FileInfo(
                filename=video_path.name,
                file_path=str(video_path),
                file_type="video",
                role=FileRole.PRIMARY,
            )
        ]
        clean_job_manager._persist_job(job)

        cleaned = await clean_job_manager.cleanup_orphaned_pending_jobs(set())

        assert cleaned == 0
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.PENDING
        assert updated.error is None


class TestJobManagerPersistence:
    """Tests for job persistence and recovery."""

    async def test_job_survives_restart(self, clean_job_manager, sample_job_config, temp_dir):
        """Jobs should be loadable after simulated restart."""
        from gpstitch.services.job_manager import JobManager

        job = await clean_job_manager.create_job(sample_job_config)
        job_id = job.id

        # Create new manager with same state_dir
        new_manager = JobManager(state_dir=clean_job_manager.state_dir)

        restored = await new_manager.get_job(job_id)

        assert restored is not None
        assert restored.config.session_id == sample_job_config.session_id

    async def test_persist_load_handles_non_ascii_log_lines(self, clean_job_manager, sample_job_config, monkeypatch):
        """Non-ASCII log lines (e.g. pillarbox '→') must round-trip on Windows-like locales.

        Reproduces the cp1252 UnicodeEncodeError seen on Windows by forcing Path.write_text /
        Path.read_text to default to cp1252 when encoding is not explicitly passed. The fix
        is to pass encoding='utf-8' in _persist_job / _load_jobs.
        """
        from pathlib import Path as _P

        from gpstitch.services.job_manager import JobManager

        orig_wt = _P.write_text
        orig_rt = _P.read_text

        def wt(self, data, encoding=None, errors=None, newline=None):
            return orig_wt(self, data, encoding=encoding or "cp1252", errors=errors, newline=newline)

        def rt(self, encoding=None, errors=None, newline=None):
            return orig_rt(self, encoding=encoding or "cp1252", errors=errors)

        monkeypatch.setattr(_P, "write_text", wt)
        monkeypatch.setattr(_P, "read_text", rt)

        job = await clean_job_manager.create_job(sample_job_config)
        # The exact log line emitted by render_service._create_pillarboxed_video.
        job.log_lines.append("Video: 3840x2880 → Canvas: 3840x2880")

        # Without the fix this raises UnicodeEncodeError under the cp1252 simulation.
        clean_job_manager._persist_job(job)

        # And reload must preserve the arrow.
        new_mgr = JobManager(state_dir=clean_job_manager.state_dir)
        restored = await new_mgr.get_job(job.id)
        assert restored is not None
        assert any("→" in line for line in restored.log_lines)

    async def test_running_job_marked_failed_on_restart(self, clean_job_manager, sample_job_config, temp_dir):
        """Running jobs should be marked as failed on restart."""
        from gpstitch.services.job_manager import JobManager

        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)
        job_id = job.id

        # Create new manager (simulates restart)
        new_manager = JobManager(state_dir=clean_job_manager.state_dir)

        restored = await new_manager.get_job(job_id)

        assert restored.status == JobStatus.FAILED
        assert "restarted" in restored.error.lower()
