"""Job management service for background render tasks."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gpstitch.config import settings
from gpstitch.models.job import Job, JobProgress, JobStatus, JobType, RenderJobConfig
from gpstitch.models.schemas import FileInfo, FileRole

logger = logging.getLogger(__name__)


class JobManager:
    """Manages background jobs with persistence and recovery."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or (settings.temp_dir / "jobs")
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # In-memory job registry
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

        # Running jobs. _current_job_id is kept for older callers/tests that
        # still expect a single current job, and points to the oldest running job.
        self._running_job_ids: set[str] = set()
        self._current_job_id: str | None = None

        # Load persisted jobs on startup
        self._load_jobs()

    def _job_file_path(self, job_id: str) -> Path:
        """Get path to job state file."""
        return self.state_dir / f"{job_id}.json"

    def _load_jobs(self):
        """Load persisted jobs from disk."""
        for job_file in self.state_dir.glob("*.json"):
            try:
                job_data = json.loads(job_file.read_text(encoding="utf-8"))
                job = Job.model_validate(job_data)
                self._jobs[job.id] = job

                # Mark previously running jobs as failed (server restart)
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.error = "Server restarted during execution"
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    logger.warning(f"Marked job {job.id} as failed due to server restart")

                # Mark old pending jobs with local sessions as failed when they
                # have no file snapshot to restore after restart.
                elif (
                    job.status == JobStatus.PENDING
                    and job.config.session_id.startswith("local:")
                    and not job.session_files
                ):
                    job.status = JobStatus.FAILED
                    job.error = "Server restarted - local session lost"
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    logger.warning(f"Marked job {job.id} as failed - local session lost on restart")

            except Exception as e:
                logger.error(f"Failed to load job from {job_file}: {e}")

    def _persist_job(self, job: Job):
        """Persist job state to disk."""
        job_file = self._job_file_path(job.id)
        job_file.write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def _snapshot_session_files(self, config: RenderJobConfig) -> list[FileInfo]:
        """Capture the files behind a render session so queued jobs can be retried after restart."""
        try:
            from gpstitch.services.file_manager import file_manager

            return list(file_manager.get_files(config.session_id))
        except Exception:
            return []

    async def create_job(self, config: RenderJobConfig) -> Job:
        """Create a new render job."""
        async with self._lock:
            job = Job(
                id=str(uuid4()),
                type=JobType.RENDER,
                status=JobStatus.PENDING,
                config=config,
                created_at=datetime.now(UTC),
                session_files=self._snapshot_session_files(config),
            )

            self._jobs[job.id] = job
            self._persist_job(job)

            logger.info(f"Created job {job.id} for session {config.session_id}")
            return job

    async def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        return self._jobs.get(job_id)

    async def list_jobs(self, limit: int | None = None) -> list[Job]:
        """List recent jobs, newest first."""
        jobs = [
            job
            for _, job in sorted(
                enumerate(self._jobs.values()),
                key=lambda item: (item[1].created_at, item[0]),
                reverse=True,
            )
        ]
        if limit is None:
            return jobs
        return jobs[:limit]

    async def count_jobs(self) -> int:
        """Count all jobs in the task queue."""
        return len(self._jobs)

    def _running_jobs_unlocked(self) -> list[Job]:
        """Return running jobs in stable FIFO order."""
        jobs = [j for j in self._jobs.values() if j.status == JobStatus.RUNNING]
        return sorted(jobs, key=lambda j: j.started_at or j.created_at)

    def _sync_current_job_unlocked(self) -> None:
        """Refresh compatibility fields from actual job statuses."""
        running_jobs = self._running_jobs_unlocked()
        self._running_job_ids = {job.id for job in running_jobs}
        self._current_job_id = running_jobs[0].id if running_jobs else None

    async def get_current_job(self) -> Job | None:
        """Get the oldest currently running job, if any."""
        self._sync_current_job_unlocked()
        return self._jobs.get(self._current_job_id) if self._current_job_id else None

    async def get_running_jobs(self) -> list[Job]:
        """Get all currently running jobs."""
        self._sync_current_job_unlocked()
        return self._running_jobs_unlocked()

    async def active_job_count(self) -> int:
        """Count currently running jobs."""
        self._sync_current_job_unlocked()
        return len(self._running_job_ids)

    async def has_active_job(self) -> bool:
        """Check if there's at least one active job running."""
        return await self.active_job_count() > 0

    async def update_job_status(self, job_id: str, status: JobStatus, error: str | None = None):
        """Update job status."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job.status = status
            if error:
                job.error = error

            if status == JobStatus.RUNNING:
                job.started_at = datetime.now(UTC)
                self._running_job_ids.add(job_id)
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.completed_at = datetime.now(UTC)
                self._running_job_ids.discard(job_id)

            self._sync_current_job_unlocked()

            self._persist_job(job)
            logger.info(f"Job {job_id} status updated to {status}")

    async def update_job_progress(
        self,
        job_id: str,
        percent: float,
        current_frame: int | None = None,
        total_frames: int | None = None,
        fps: float | None = None,
        eta_seconds: float | None = None,
    ):
        """Update job progress."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job.progress.percent = min(percent, 100.0)
            if current_frame is not None:
                job.progress.current_frame = current_frame
            if total_frames is not None:
                job.progress.total_frames = total_frames
            if fps is not None:
                job.progress.fps = fps
            if eta_seconds is not None:
                job.progress.eta_seconds = eta_seconds

            # Persist periodically (every 5% or every 100 frames)
            should_persist = int(percent) % 5 == 0 or (current_frame and current_frame % 100 == 0)
            if should_persist:
                self._persist_job(job)

    async def append_job_log(self, job_id: str, line: str):
        """Append a line to job log."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            # Keep last 500 lines to prevent memory issues
            job.log_lines.append(line)
            if len(job.log_lines) > 500:
                job.log_lines = job.log_lines[-500:]

    async def reset_job_for_retry(self, job_id: str, error: str) -> bool:
        """Requeue a failed render attempt if retry budget remains."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status == JobStatus.CANCELLED or job.retry_count >= job.max_retries:
                return False

            job.retry_count += 1
            job.status = JobStatus.PENDING
            job.started_at = None
            job.completed_at = None
            job.progress = JobProgress()
            job.error = None
            job.pid = None
            self._running_job_ids.discard(job_id)

            job.log_lines.append(f"\n=== Retry {job.retry_count}/{job.max_retries} ===")
            job.log_lines.append(f"Previous failure: {error}")
            if len(job.log_lines) > 500:
                job.log_lines = job.log_lines[-500:]

            self._sync_current_job_unlocked()
            self._persist_job(job)
            logger.warning(
                "Requeued job %s for retry %s/%s after failure: %s",
                job_id,
                job.retry_count,
                job.max_retries,
                error,
            )
            return True

    async def retry_failed_job(self, job_id: str, reason: str = "Manual retry requested") -> bool:
        """Requeue a failed job from a user-triggered retry action."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.FAILED:
                return False

            job.status = JobStatus.PENDING
            job.started_at = None
            job.completed_at = None
            job.progress = JobProgress()
            job.error = None
            job.pid = None
            # Manual retries start a fresh automatic retry budget.
            job.retry_count = 0
            self._running_job_ids.discard(job_id)

            job.log_lines.append("\n=== Manual retry ===")
            job.log_lines.append(reason)
            if len(job.log_lines) > 500:
                job.log_lines = job.log_lines[-500:]

            self._sync_current_job_unlocked()
            self._persist_job(job)
            logger.info("Manually requeued failed job %s", job_id)
            return True

    async def set_job_session_files(self, job_id: str, files: list[FileInfo]) -> None:
        """Persist a recovered render session file snapshot for future retries."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.session_files = list(files)
            self._persist_job(job)

    async def set_job_pid(self, job_id: str, pid: int):
        """Set the process ID for a running job."""
        job = self._jobs.get(job_id)
        if job:
            job.pid = pid
            self._persist_job(job)

    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove old completed/failed jobs."""
        async with self._lock:
            now = datetime.now(UTC)
            to_remove = []

            for job_id, job in self._jobs.items():
                if job.is_terminal() and job.completed_at:
                    age_hours = (now - job.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]
                job_file = self._job_file_path(job_id)
                if job_file.exists():
                    job_file.unlink()
                logger.info(f"Cleaned up old job {job_id}")

            return len(to_remove)

    async def remove_jobs_by_status(self, statuses: set[JobStatus]) -> int:
        """Remove terminal jobs matching the given statuses."""
        async with self._lock:
            to_remove = [
                job_id
                for job_id, job in self._jobs.items()
                if job.is_terminal() and job.status in statuses
            ]

            for job_id in to_remove:
                del self._jobs[job_id]
                job_file = self._job_file_path(job_id)
                if job_file.exists():
                    job_file.unlink()
                logger.info(f"Removed terminal job {job_id}")

            self._sync_current_job_unlocked()
            return len(to_remove)

    async def get_next_pending_job(self) -> Job | None:
        """Get the next pending job from queue (FIFO by created_at)."""
        jobs = await self.get_next_pending_jobs(1)
        return jobs[0] if jobs else None

    async def get_next_pending_jobs(self, limit: int = 1) -> list[Job]:
        """Get the next pending jobs from queue (FIFO by created_at)."""
        pending = [j for j in self._jobs.values() if j.status == JobStatus.PENDING]
        if not pending or limit <= 0:
            return []
        return sorted(pending, key=lambda j: j.created_at)[:limit]

    async def has_pending_jobs(self) -> bool:
        """Check if there are pending jobs in queue."""
        return any(j.status == JobStatus.PENDING for j in self._jobs.values())

    async def has_unfinished_jobs(self) -> bool:
        """Check if any job is still queued or running."""
        return any(j.status in (JobStatus.PENDING, JobStatus.RUNNING) for j in self._jobs.values())

    async def get_latest_job(self) -> Job | None:
        """Return the most recently created job, if any."""
        jobs = await self.list_jobs(limit=1)
        return jobs[0] if jobs else None

    async def count_batch_jobs(self, batch_id: str) -> dict:
        """Count jobs in a batch by status."""
        jobs = await self.get_batch_jobs(batch_id)
        return {
            "total": len(jobs),
            "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING),
            "running": sum(1 for j in jobs if j.status == JobStatus.RUNNING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "cancelled": sum(1 for j in jobs if j.status == JobStatus.CANCELLED),
        }

    async def get_batch_jobs(self, batch_id: str) -> list[Job]:
        """Get all jobs in a batch in creation order."""
        jobs = [j for j in self._jobs.values() if j.batch_id == batch_id]
        return sorted(jobs, key=lambda j: j.created_at)

    async def create_job_with_batch(self, config: RenderJobConfig, batch_id: str | None = None) -> Job:
        """Create a new render job with optional batch ID."""
        async with self._lock:
            job = Job(
                id=str(uuid4()),
                type=JobType.RENDER,
                status=JobStatus.PENDING,
                config=config,
                created_at=datetime.now(UTC),
                batch_id=batch_id,
                session_files=self._snapshot_session_files(config),
            )

            self._jobs[job.id] = job
            self._persist_job(job)

            logger.info(
                f"Created job {job.id} for session {config.session_id}" + (f" (batch {batch_id})" if batch_id else "")
            )
            return job

    async def cancel_batch_pending_jobs(self, batch_id: str) -> int:
        """Cancel all pending jobs in a batch. Returns count of cancelled jobs."""
        cancelled = 0
        async with self._lock:
            for job in self._jobs.values():
                if job.batch_id == batch_id and job.status == JobStatus.PENDING:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    cancelled += 1
                    logger.info(f"Cancelled pending job {job.id} from batch {batch_id}")
        return cancelled

    async def get_running_batch_job(self, batch_id: str) -> Job | None:
        """Get the running job in a batch, if any."""
        jobs = await self.get_running_batch_jobs(batch_id)
        return jobs[0] if jobs else None

    async def get_running_batch_jobs(self, batch_id: str) -> list[Job]:
        """Get all running jobs in a batch."""
        jobs = [job for job in self._jobs.values() if job.batch_id == batch_id and job.status == JobStatus.RUNNING]
        return sorted(jobs, key=lambda j: j.started_at or j.created_at)

    @staticmethod
    def _has_restorable_local_session(job: Job) -> bool:
        """Return whether a local job has persisted file data that can recreate its session."""
        if not job.config.session_id.startswith("local:") or not job.session_files:
            return False

        primary = next((file for file in job.session_files if file.role == FileRole.PRIMARY), None)
        return bool(primary and Path(primary.file_path).exists())

    async def cleanup_orphaned_pending_jobs(self, valid_session_ids: set) -> int:
        """Mark pending jobs as failed if their session no longer exists.

        Args:
            valid_session_ids: Set of session IDs that currently exist

        Returns:
            Number of jobs marked as failed
        """
        cleaned = 0
        async with self._lock:
            for job in self._jobs.values():
                if job.status == JobStatus.PENDING and job.config.session_id not in valid_session_ids:
                    if self._has_restorable_local_session(job):
                        logger.info(
                            "Preserving pending job %s with restorable local session snapshot",
                            job.id,
                        )
                        continue
                    job.status = JobStatus.FAILED
                    job.error = "Session no longer exists (orphaned job)"
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    cleaned += 1
                    logger.info(f"Cleaned up orphaned job {job.id} (session {job.config.session_id})")
        return cleaned


# Global job manager instance
job_manager = JobManager()
