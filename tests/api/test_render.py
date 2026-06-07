"""API tests for render endpoints."""

from unittest.mock import AsyncMock

import pytest

from gpstitch.models.job import JobStatus, RenderJobConfig
from gpstitch.api import render as render_api
from gpstitch.services import render_service as render_service_module
from gpstitch.services.job_manager import job_manager
from gpstitch.services.render_service import render_service


class FakeRuntimeSettings:
    def __init__(self):
        self.render_concurrency = 1
        self.shutdown_after_all_tasks = False

    def get_render_concurrency(self, default: int = 1) -> int:
        return self.render_concurrency or default

    def set_render_concurrency(self, value: int) -> int:
        self.render_concurrency = max(1, min(3, int(value)))
        return self.render_concurrency

    def get_shutdown_after_all_tasks(self, default: bool = False) -> bool:
        return self.shutdown_after_all_tasks

    def set_shutdown_after_all_tasks(self, enabled: bool) -> bool:
        self.shutdown_after_all_tasks = bool(enabled)
        return self.shutdown_after_all_tasks


@pytest.fixture
def isolated_render_jobs(monkeypatch):
    """Isolate global render jobs for API tests that inspect the task queue."""
    old_jobs = dict(job_manager._jobs)
    old_current_job_id = job_manager._current_job_id
    old_running_job_ids = set(getattr(job_manager, "_running_job_ids", set()))
    old_concurrency = render_service._concurrency
    old_active_job_ids = set(render_service._active_job_ids)
    old_processes = dict(render_service._processes)
    old_service_current_job_id = render_service._current_job_id
    old_service_process = render_service._process
    old_shutdown_armed = render_service._shutdown_after_all_tasks_armed
    fake_runtime_settings = FakeRuntimeSettings()

    monkeypatch.setattr(job_manager, "_persist_job", lambda job: None)
    monkeypatch.setattr(render_service_module, "runtime_settings_service", fake_runtime_settings)
    monkeypatch.setattr(render_api, "runtime_settings_service", fake_runtime_settings)
    job_manager._jobs.clear()
    job_manager._current_job_id = None
    job_manager._running_job_ids.clear()
    render_service._concurrency = 1
    render_service._active_job_ids.clear()
    render_service._processes.clear()
    render_service._current_job_id = None
    render_service._process = None
    render_service._shutdown_after_all_tasks_armed = False

    yield fake_runtime_settings

    job_manager._jobs.clear()
    job_manager._jobs.update(old_jobs)
    job_manager._current_job_id = old_current_job_id
    job_manager._running_job_ids.clear()
    job_manager._running_job_ids.update(old_running_job_ids)
    render_service._concurrency = old_concurrency
    render_service._active_job_ids.clear()
    render_service._active_job_ids.update(old_active_job_ids)
    render_service._processes.clear()
    render_service._processes.update(old_processes)
    render_service._current_job_id = old_service_current_job_id
    render_service._process = old_service_process
    render_service._shutdown_after_all_tasks_armed = old_shutdown_armed


class TestRenderJobs:
    """Tests for render job endpoints."""

    async def test_get_current_job_none(self, async_client):
        """GET /api/render/current when no job running."""
        response = await async_client.get("/api/render/current")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] is None

    async def test_list_render_jobs(self, async_client, isolated_render_jobs, temp_dir):
        """GET /api/render/jobs returns recent render jobs for task management."""
        output_file = temp_dir / "queued_overlay.mp4"
        job = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-list-session",
                layout="default-1920x1080",
                output_file=str(output_file),
            )
        )
        await job_manager.update_job_progress(job.id, 42.5, current_frame=120, total_frames=300, fps=25.0)
        job.retry_count = 1

        response = await async_client.get("/api/render/jobs")

        assert response.status_code == 200
        data = response.json()
        item = next(item for item in data["jobs"] if item["job_id"] == job.id)
        assert item["status"] == "pending"
        assert item["video_name"] == output_file.name
        assert item["output_file"] == str(output_file)
        assert item["progress"]["percent"] == 42.5
        assert item["progress"]["current_frame"] == 120
        assert item["can_cancel"] is True
        assert item["retry_count"] == 1
        assert item["max_retries"] == 3
        assert data["render_concurrency"] == 1
        assert data["shutdown_after_all_tasks"] is False
        assert isinstance(data["shutdown_supported"], bool)

    async def test_list_render_jobs_returns_full_queue_by_default(
        self,
        async_client,
        isolated_render_jobs,
        temp_dir,
    ):
        """Task Manager should not silently hide jobs after the first 100."""
        created_ids = []
        for index in range(125):
            job = await job_manager.create_job(
                RenderJobConfig(
                    session_id=f"task-list-session-{index}",
                    layout="default-1920x1080",
                    output_file=str(temp_dir / f"queued_{index}_overlay.mp4"),
                )
            )
            created_ids.append(job.id)

        response = await async_client.get("/api/render/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 125
        assert len(data["jobs"]) == 125
        assert {job["job_id"] for job in data["jobs"]} == set(created_ids)

    async def test_list_render_jobs_limit_keeps_total_count(
        self,
        async_client,
        isolated_render_jobs,
        temp_dir,
    ):
        """Explicit list limits should page the payload without changing total."""
        for index in range(125):
            await job_manager.create_job(
                RenderJobConfig(
                    session_id=f"task-list-limited-session-{index}",
                    layout="default-1920x1080",
                    output_file=str(temp_dir / f"limited_{index}_overlay.mp4"),
                )
            )

        response = await async_client.get("/api/render/jobs?limit=100")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 125
        assert len(data["jobs"]) == 100

    async def test_cancel_pending_render_job(self, async_client, isolated_render_jobs, temp_dir):
        """POST /api/render/cancel/{job_id} can cancel a queued task."""
        job = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-cancel-session",
                layout="default-1920x1080",
                output_file=str(temp_dir / "queued_overlay.mp4"),
            )
        )

        response = await async_client.post(f"/api/render/cancel/{job.id}")

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        stored = await job_manager.get_job(job.id)
        assert stored.status == JobStatus.CANCELLED

    async def test_clear_finished_render_jobs(self, async_client, isolated_render_jobs, temp_dir):
        """POST /api/render/jobs/clear removes only finished jobs."""
        completed = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-clear-completed",
                layout="default-1920x1080",
                output_file=str(temp_dir / "completed_overlay.mp4"),
            )
        )
        failed = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-clear-failed",
                layout="default-1920x1080",
                output_file=str(temp_dir / "failed_overlay.mp4"),
            )
        )
        cancelled = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-clear-cancelled",
                layout="default-1920x1080",
                output_file=str(temp_dir / "cancelled_overlay.mp4"),
            )
        )
        pending = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-clear-pending",
                layout="default-1920x1080",
                output_file=str(temp_dir / "pending_overlay.mp4"),
            )
        )

        await job_manager.update_job_status(completed.id, JobStatus.COMPLETED)
        await job_manager.update_job_status(failed.id, JobStatus.FAILED, error="failed")
        await job_manager.update_job_status(cancelled.id, JobStatus.CANCELLED)

        response = await async_client.post(
            "/api/render/jobs/clear",
            json={"statuses": ["completed", "failed", "cancelled"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["removed"] == 3
        assert data["statuses"] == ["completed", "failed", "cancelled"]
        assert await job_manager.get_job(completed.id) is None
        assert await job_manager.get_job(failed.id) is None
        assert await job_manager.get_job(cancelled.id) is None
        assert await job_manager.get_job(pending.id) is not None

    async def test_clear_render_jobs_rejects_non_terminal_status(self, async_client, isolated_render_jobs):
        """The cleanup endpoint must not accept queued or running job statuses."""
        response = await async_client.post(
            "/api/render/jobs/clear",
            json={"statuses": ["failed", "running"]},
        )

        assert response.status_code == 400
        assert "Only finished jobs" in response.json()["detail"]

    async def test_cancel_reserved_pending_render_job(self, async_client, isolated_render_jobs, temp_dir):
        """A job reserved by the render service but not spawned yet can still be cancelled."""
        job = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-reserved-cancel-session",
                layout="default-1920x1080",
                output_file=str(temp_dir / "reserved_overlay.mp4"),
            )
        )
        render_service._active_job_ids.add(job.id)

        response = await async_client.post(f"/api/render/cancel/{job.id}")

        assert response.status_code == 200
        stored = await job_manager.get_job(job.id)
        assert stored.status == JobStatus.CANCELLED
        assert job.id not in render_service._active_job_ids

    async def test_retry_failed_render_jobs_requeues_selection(
        self,
        async_client,
        isolated_render_jobs,
        temp_dir,
        monkeypatch,
    ):
        """Selected failed jobs can be manually retried after automatic retries are exhausted."""
        monkeypatch.setattr(render_api.render_service, "kick_queue", AsyncMock())
        failed = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-retry-failed-session",
                layout="default-1920x1080",
                output_file=str(temp_dir / "failed_overlay.mp4"),
            )
        )
        await job_manager.update_job_status(failed.id, JobStatus.FAILED, error="exhausted")
        failed = await job_manager.get_job(failed.id)
        failed.retry_count = failed.max_retries

        response = await async_client.post(
            "/api/render/jobs/retry",
            json={"job_ids": [failed.id, failed.id]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["requested"] == 1
        assert data["affected"] == 1
        assert data["skipped"] == 0
        stored = await job_manager.get_job(failed.id)
        assert stored.status == JobStatus.PENDING
        assert stored.retry_count == 0
        assert stored.error is None
        assert any("Manual retry" in line for line in stored.log_lines)
        render_api.render_service.kick_queue.assert_awaited_once()

    async def test_cancel_selected_render_jobs_cancels_pending_jobs(
        self,
        async_client,
        isolated_render_jobs,
        temp_dir,
        monkeypatch,
    ):
        """Selected queued jobs can be cancelled in one request."""
        monkeypatch.setattr(render_api.render_service, "kick_queue", AsyncMock())
        first = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-bulk-cancel-1",
                layout="default-1920x1080",
                output_file=str(temp_dir / "first_overlay.mp4"),
            )
        )
        second = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-bulk-cancel-2",
                layout="default-1920x1080",
                output_file=str(temp_dir / "second_overlay.mp4"),
            )
        )
        failed = await job_manager.create_job(
            RenderJobConfig(
                session_id="task-bulk-cancel-failed",
                layout="default-1920x1080",
                output_file=str(temp_dir / "failed_overlay.mp4"),
            )
        )
        await job_manager.update_job_status(failed.id, JobStatus.FAILED, error="already failed")

        response = await async_client.post(
            "/api/render/jobs/cancel",
            json={"job_ids": [first.id, second.id, failed.id]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["requested"] == 3
        assert data["affected"] == 2
        assert data["skipped"] == 1
        assert (await job_manager.get_job(first.id)).status == JobStatus.CANCELLED
        assert (await job_manager.get_job(second.id)).status == JobStatus.CANCELLED
        assert (await job_manager.get_job(failed.id)).status == JobStatus.FAILED
        render_api.render_service.kick_queue.assert_awaited_once()

    async def test_batch_status_returns_all_running_jobs(self, async_client, isolated_render_jobs, temp_dir):
        """Batch status exposes every running job while keeping current_job compatibility."""
        batch_id = "batch-running-status"
        first = await job_manager.create_job_with_batch(
            RenderJobConfig(
                session_id="batch-running-1",
                layout="default-1920x1080",
                output_file=str(temp_dir / "first_overlay.mp4"),
            ),
            batch_id=batch_id,
        )
        second = await job_manager.create_job_with_batch(
            RenderJobConfig(
                session_id="batch-running-2",
                layout="default-1920x1080",
                output_file=str(temp_dir / "second_overlay.mp4"),
            ),
            batch_id=batch_id,
        )
        await job_manager.update_job_status(first.id, JobStatus.RUNNING)
        await job_manager.update_job_status(second.id, JobStatus.RUNNING)

        response = await async_client.get(f"/api/render/batch/{batch_id}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] == 2
        assert data["current_job"]["job_id"] == first.id
        assert [job["job_id"] for job in data["running_jobs"]] == [first.id, second.id]

    async def test_render_concurrency_can_be_configured(self, async_client, isolated_render_jobs):
        """Render concurrency can be adjusted at runtime."""
        response = await async_client.get("/api/render/concurrency")
        assert response.status_code == 200
        assert response.json()["concurrency"] == 1

        response = await async_client.put("/api/render/concurrency", json={"concurrency": 2})
        assert response.status_code == 200
        assert response.json()["concurrency"] == 2

        response = await async_client.get("/api/render/jobs")
        assert response.status_code == 200
        assert response.json()["render_concurrency"] == 2
        assert isolated_render_jobs.render_concurrency == 2

    async def test_render_concurrency_rejects_invalid_values(self, async_client, isolated_render_jobs):
        """Only 1, 2, or 3 render workers are allowed."""
        response = await async_client.put("/api/render/concurrency", json={"concurrency": 4})
        assert response.status_code == 422

    async def test_task_shutdown_setting_can_be_configured(self, async_client, isolated_render_jobs):
        """Task-manager shutdown setting is persisted through the runtime settings service."""
        response = await async_client.get("/api/render/task-shutdown")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        response = await async_client.put("/api/render/task-shutdown", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["enabled"] is True

        response = await async_client.get("/api/render/jobs")
        assert response.status_code == 200
        assert response.json()["shutdown_after_all_tasks"] is True
        assert isolated_render_jobs.shutdown_after_all_tasks is True


class TestCommandGeneration:
    """Tests for command generation endpoint."""

    async def test_generate_command(self, async_client, api_test_video):
        """POST /api/command generates CLI command."""
        # Create session
        upload_resp = await async_client.post("/api/local-file", json={"file_path": str(api_test_video)})
        session_id = upload_resp.json()["session_id"]

        # Generate command
        response = await async_client.post(
            "/api/command",
            json={
                "session_id": session_id,
                "layout": "default-1920x1080",
                "output_filename": "output.mp4",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "command" in data
        assert "input_file" in data
        assert "gpstitch-dashboard" in data["command"]
        assert str(api_test_video) in data["input_file"]

    async def test_generate_command_with_units(self, async_client, api_test_video):
        """POST /api/command with custom units."""
        # Create session
        upload_resp = await async_client.post("/api/local-file", json={"file_path": str(api_test_video)})
        session_id = upload_resp.json()["session_id"]

        # Generate command with units
        response = await async_client.post(
            "/api/command",
            json={
                "session_id": session_id,
                "layout": "default-1920x1080",
                "output_filename": "output.mp4",
                "units_speed": "mph",
                "units_altitude": "feet",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "mph" in data["command"]
        assert "feet" in data["command"]

    async def test_generate_command_invalid_session(self, async_client):
        """POST /api/command with invalid session returns 404."""
        response = await async_client.post(
            "/api/command",
            json={
                "session_id": "invalid-session",
                "layout": "default",
                "output_filename": "output.mp4",
            },
        )

        assert response.status_code == 404


class TestLayoutsAndOptions:
    """Tests for layouts and options endpoints."""

    async def test_get_layouts(self, async_client):
        """GET /api/layouts returns available layouts."""
        response = await async_client.get("/api/layouts")

        assert response.status_code == 200
        data = response.json()
        assert "layouts" in data
        assert len(data["layouts"]) > 0

    async def test_layouts_have_dimensions(self, async_client):
        """Layouts include dimensions."""
        response = await async_client.get("/api/layouts")
        data = response.json()

        for layout in data["layouts"]:
            assert "name" in layout
            assert "width" in layout
            assert "height" in layout
            assert layout["width"] > 0
            assert layout["height"] > 0

    async def test_get_unit_options(self, async_client):
        """GET /api/options/units returns unit options."""
        response = await async_client.get("/api/options/units")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) > 0

    async def test_unit_options_have_categories(self, async_client):
        """Unit options have expected categories."""
        response = await async_client.get("/api/options/units")
        data = response.json()

        category_names = [c["name"] for c in data["categories"]]
        assert "speed" in category_names
        assert "altitude" in category_names

    async def test_get_map_styles(self, async_client):
        """GET /api/options/map-styles returns map styles."""
        response = await async_client.get("/api/options/map-styles")

        assert response.status_code == 200
        data = response.json()
        assert "styles" in data
        assert len(data["styles"]) > 0

    async def test_get_ffmpeg_profiles(self, async_client):
        """GET /api/options/ffmpeg-profiles returns profiles."""
        response = await async_client.get("/api/options/ffmpeg-profiles")

        assert response.status_code == 200
        data = response.json()
        assert "profiles" in data
        assert len(data["profiles"]) > 0
