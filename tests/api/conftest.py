"""API test fixtures."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolate_api_runtime_state(monkeypatch):
    """Keep API tests from persisting fake jobs into the user's runtime queue."""
    from gpstitch.services.file_manager import file_manager
    from gpstitch.services.job_manager import job_manager
    from gpstitch.services.render_service import render_service

    old_jobs = dict(job_manager._jobs)
    old_current_job_id = job_manager._current_job_id
    old_running_job_ids = set(getattr(job_manager, "_running_job_ids", set()))
    old_file_current_session = file_manager._current_session
    old_local_sessions = {session_id: list(files) for session_id, files in file_manager._local_sessions.items()}
    old_render_active_job_ids = set(render_service._active_job_ids)
    old_render_processes = dict(render_service._processes)
    old_render_current_job_id = render_service._current_job_id
    old_render_process = render_service._process

    monkeypatch.setattr(job_manager, "_persist_job", lambda job: None)
    job_manager._jobs.clear()
    job_manager._current_job_id = None
    job_manager._running_job_ids.clear()
    file_manager._current_session = None
    file_manager._local_sessions.clear()
    render_service._active_job_ids.clear()
    render_service._processes.clear()
    render_service._current_job_id = None
    render_service._process = None

    yield

    job_manager._jobs.clear()
    job_manager._jobs.update(old_jobs)
    job_manager._current_job_id = old_current_job_id
    job_manager._running_job_ids.clear()
    job_manager._running_job_ids.update(old_running_job_ids)
    file_manager._current_session = old_file_current_session
    file_manager._local_sessions.clear()
    file_manager._local_sessions.update(old_local_sessions)
    render_service._active_job_ids.clear()
    render_service._active_job_ids.update(old_render_active_job_ids)
    render_service._processes.clear()
    render_service._processes.update(old_render_processes)
    render_service._current_job_id = old_render_current_job_id
    render_service._process = old_render_process


@pytest.fixture
def api_test_video():
    """Real test video for API tests (skips if not available)."""
    from tests.fixtures.data import TEST_VIDEO_PATH

    path = Path(TEST_VIDEO_PATH)
    if not path.exists():
        pytest.skip(f"API test video not found: {path}")
    return path


@pytest.fixture
def mock_render_service():
    """Mock render_service for API tests that don't need real rendering."""
    mock = MagicMock()
    mock.start_render = AsyncMock(return_value=None)
    mock.cancel_render = AsyncMock(return_value=True)
    return mock
