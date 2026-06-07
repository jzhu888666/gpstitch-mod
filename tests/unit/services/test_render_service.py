"""Unit tests for render_service - process cancellation, cleanup, and mtime alignment."""

import asyncio
import datetime
import signal
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCancelRender:
    """Tests for cancel_render method - killing process groups."""

    @pytest.fixture
    def render_service(self):
        """Create a fresh RenderService instance."""
        # Import here to avoid side effects from patches
        from gpstitch.services.render_service import RenderService

        service = RenderService()
        return service

    @pytest.fixture
    def mock_process(self):
        """Create a mock subprocess."""
        process = MagicMock()
        process.pid = 12345
        process.wait = AsyncMock(return_value=0)
        return process

    async def test_cancel_render_wrong_job_id(self, render_service):
        """Cancel returns False if job_id doesn't match current job."""
        render_service._current_job_id = "job-123"

        result = await render_service.cancel_render("job-456")

        assert result is False

    async def test_cancel_render_no_process(self, render_service):
        """Cancel returns False if no process is running."""
        render_service._current_job_id = "job-123"
        render_service._process = None

        result = await render_service.cancel_render("job-123")

        assert result is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_cancel_render_kills_process_group_unix(self, render_service, mock_process):
        """On Unix, cancel_render should kill entire process group."""
        render_service._current_job_id = "job-123"
        render_service._process = mock_process

        with (
            patch("os.killpg") as mock_killpg,
            patch("gpstitch.services.render_service.job_manager") as mock_job_manager,
        ):
            mock_job_manager.update_job_status = AsyncMock()

            result = await render_service.cancel_render("job-123")

            assert result is True
            # Should call killpg with SIGTERM first
            mock_killpg.assert_called_with(12345, signal.SIGTERM)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_cancel_render_force_kills_on_timeout(self, render_service, mock_process):
        """On timeout, cancel_render should force kill with SIGKILL."""
        render_service._current_job_id = "job-123"
        render_service._process = mock_process

        # Make wait() timeout
        async def slow_wait():
            await asyncio.sleep(10)

        mock_process.wait = slow_wait

        with (
            patch("os.killpg") as mock_killpg,
            patch("gpstitch.services.render_service.job_manager") as mock_job_manager,
        ):
            mock_job_manager.update_job_status = AsyncMock()

            # Use shorter timeout for test
            with patch("asyncio.wait_for", side_effect=TimeoutError):
                # Create a fast completing wait for after SIGKILL
                mock_process.wait = AsyncMock(return_value=0)

                result = await render_service.cancel_render("job-123")

            assert result is True
            # Should have called killpg twice: SIGTERM then SIGKILL
            calls = mock_killpg.call_args_list
            assert len(calls) >= 1
            # Last call should be SIGKILL
            assert any(call[0][1] == signal.SIGKILL for call in calls)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_cancel_render_handles_process_already_dead(self, render_service, mock_process):
        """Cancel should handle ProcessLookupError gracefully."""
        render_service._current_job_id = "job-123"
        render_service._process = mock_process

        with (
            patch("os.killpg", side_effect=ProcessLookupError),
            patch("gpstitch.services.render_service.job_manager") as mock_job_manager,
        ):
            mock_job_manager.update_job_status = AsyncMock()

            result = await render_service.cancel_render("job-123")

            # Should still return True - process is dead
            assert result is True


class TestKillProcessTree:
    """Tests for _kill_process_tree helper method."""

    @pytest.fixture
    def render_service(self):
        """Create a fresh RenderService instance."""
        from gpstitch.services.render_service import RenderService

        return RenderService()

    @pytest.fixture
    def mock_process(self):
        """Create a mock subprocess."""
        process = MagicMock()
        process.pid = 12345
        process.wait = AsyncMock(return_value=0)
        process.kill = MagicMock()
        return process

    async def test_kill_process_tree_no_process(self, render_service):
        """Should do nothing if no process exists."""
        render_service._process = None

        # Should not raise
        await render_service._kill_process_tree()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_kill_process_tree_unix(self, render_service, mock_process):
        """On Unix, should kill entire process group with SIGKILL."""
        render_service._process = mock_process

        with patch("os.killpg") as mock_killpg:
            await render_service._kill_process_tree()

            mock_killpg.assert_called_once_with(12345, signal.SIGKILL)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    async def test_kill_process_tree_windows(self, render_service, mock_process):
        """On Windows, should call process.kill()."""
        render_service._process = mock_process

        await render_service._kill_process_tree()

        mock_process.kill.assert_called_once()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_kill_process_tree_handles_already_dead(self, render_service, mock_process):
        """Should handle ProcessLookupError gracefully."""
        render_service._process = mock_process

        with patch("os.killpg", side_effect=ProcessLookupError):
            # Should not raise
            await render_service._kill_process_tree()


class TestFfmpegOutputDiagnostics:
    """Tests for surfacing the FFmpeg stderr file written by gopro_overlay."""

    def test_read_ffmpeg_output_tail(self, tmp_path):
        from gpstitch.services.render_service import RenderService

        ffmpeg_log = tmp_path / "ffmpeg.txt"
        ffmpeg_log.write_text(
            "\n".join(
                [
                    "frame setup",
                    "[hwupload @ 000001] A hardware device reference is required to upload frames to.",
                    "[AVFilterGraph @ 000002] Error initializing filters",
                    "Error : Invalid argument",
                ]
            ),
            encoding="utf-8",
        )

        lines = RenderService._read_ffmpeg_output_tail(
            [
                "Generating overlay",
                f"FFMPEG Output is in {ffmpeg_log}",
                "OSError: [Errno 22] Invalid argument",
            ],
            max_lines=3,
        )

        assert lines == [
            "ffmpeg: [hwupload @ 000001] A hardware device reference is required to upload frames to.",
            "ffmpeg: [AVFilterGraph @ 000002] Error initializing filters",
            "ffmpeg: Error : Invalid argument",
        ]

    def test_read_ffmpeg_output_tail_missing_file(self, tmp_path):
        from gpstitch.services.render_service import RenderService

        missing = tmp_path / "missing.txt"

        assert RenderService._read_ffmpeg_output_tail([f"FFMPEG Output is in {missing}"]) == []

    def test_process_error_tail_prefers_application_exception(self):
        from gpstitch.services.render_service import RenderService

        lines = RenderService._read_process_error_tail(
            [
                "FFMPEG Output is in C:\\Temp\\ffmpeg.txt",
                "ffmpeg: Stream #0:4[0x0]: Video: mjpeg (attached pic)",
                "2026-05-31 15:30:48,812 - __main__ - ERROR - Failed to execute gopro-dashboard.py: AMap snapshot rendering failed",
                "Traceback (most recent call last):",
                "gpstitch.services.amap_jsapi_renderer.AMapRenderError: AMap snapshot rendering failed",
            ]
        )

        assert lines == [
            "2026-05-31 15:30:48,812 - __main__ - ERROR - Failed to execute gopro-dashboard.py: AMap snapshot rendering failed",
            "Traceback (most recent call last):",
            "gpstitch.services.amap_jsapi_renderer.AMapRenderError: AMap snapshot rendering failed",
        ]


class TestRenderConcurrencySettings:
    """Tests for render concurrency persistence."""

    def test_render_service_loads_persisted_concurrency(self, tmp_path, monkeypatch):
        from gpstitch.services import render_service as render_service_module
        from gpstitch.services.runtime_settings import RuntimeSettingsService

        runtime_settings = RuntimeSettingsService(tmp_path / "runtime.json")
        runtime_settings.set_render_concurrency(3)

        monkeypatch.setattr(render_service_module, "runtime_settings_service", runtime_settings)

        service = render_service_module.RenderService()

        assert service.concurrency == 3

    async def test_set_concurrency_persists_value(self, tmp_path, monkeypatch):
        from gpstitch.services import render_service as render_service_module
        from gpstitch.services.runtime_settings import RuntimeSettingsService

        runtime_settings = RuntimeSettingsService(tmp_path / "runtime.json")
        monkeypatch.setattr(render_service_module, "runtime_settings_service", runtime_settings)

        service = render_service_module.RenderService()
        service.kick_queue = AsyncMock()

        assert await service.set_concurrency(2) == 2
        assert runtime_settings.get_render_concurrency(default=1) == 2
        service.kick_queue.assert_awaited_once()

    async def test_start_next_pending_job_fills_available_concurrency(self, monkeypatch):
        from gpstitch.services import render_service as render_service_module

        pending_jobs = [
            SimpleNamespace(id="job-1", config=SimpleNamespace()),
            SimpleNamespace(id="job-2", config=SimpleNamespace()),
            SimpleNamespace(id="job-3", config=SimpleNamespace()),
        ]
        fake_job_manager = SimpleNamespace(get_next_pending_jobs=AsyncMock(return_value=pending_jobs))
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)

        service = render_service_module.RenderService()
        service._concurrency = 3
        service.start_render = AsyncMock()

        await service._start_next_pending_job()
        await asyncio.sleep(0)

        fake_job_manager.get_next_pending_jobs.assert_awaited_once_with(3)
        assert service._active_job_ids == {"job-1", "job-2", "job-3"}
        assert service.start_render.await_count == 3


class TestMapCacheWarmupBeforeRender:
    """Render startup should not block on large map tile warmups."""

    async def test_warmup_is_skipped_when_render_limit_is_zero(self, monkeypatch):
        from gpstitch.services import map_cache as map_cache_module
        from gpstitch.services.render_service import RenderService

        called = False

        class WarmupService:
            def warm_session_cache(self, **_kwargs):
                nonlocal called
                called = True
                return SimpleNamespace(rendered_maps=1, capped=False, route_points=1)

        monkeypatch.setattr("gpstitch.services.render_service.settings.map_cache_render_warmup_max_tiles", 0)
        monkeypatch.setattr(map_cache_module, "map_cache_service", WarmupService())

        await RenderService()._warm_map_cache_for_job(
            "job-1",
            SimpleNamespace(
                session_id="session",
                map_style="osm",
                layout="default-1920x1080",
                layout_xml_path=None,
                language="en",
            ),
        )

        assert called is False

    async def test_warmup_uses_render_specific_tile_limit(self, monkeypatch):
        from gpstitch.services import map_cache as map_cache_module
        from gpstitch.services import render_service as render_service_module

        calls = []

        class WarmupService:
            def warm_session_cache(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(rendered_maps=2, capped=True, route_points=20)

        fake_job_manager = SimpleNamespace(append_job_log=AsyncMock())
        monkeypatch.setattr(render_service_module.settings, "map_cache_render_warmup_max_tiles", 5)
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)
        monkeypatch.setattr(map_cache_module, "map_cache_service", WarmupService())

        await render_service_module.RenderService()._warm_map_cache_for_job(
            "job-1",
            SimpleNamespace(
                session_id="session",
                map_style="osm",
                layout="default-1920x1080",
                layout_xml_path=None,
                language="en",
            ),
        )

        assert calls
        assert calls[0]["max_tiles"] == 5
        fake_job_manager.append_job_log.assert_awaited_once()


class TestShutdownAfterAllTasks:
    """Tests for task-manager shutdown scheduling."""

    class RuntimeSettings:
        def __init__(self, enabled: bool):
            self.enabled = enabled

        def get_render_concurrency(self, default: int = 1) -> int:
            return default

        def get_shutdown_after_all_tasks(self, default: bool = False) -> bool:
            return self.enabled

    async def test_queue_drain_schedules_shutdown(self, monkeypatch):
        from gpstitch.services import render_service as render_service_module

        fake_job_manager = SimpleNamespace(
            has_unfinished_jobs=AsyncMock(return_value=False),
            get_latest_job=AsyncMock(return_value=SimpleNamespace(id="job-1")),
            append_job_log=AsyncMock(),
        )
        fake_power = SimpleNamespace(
            schedule_shutdown_once=AsyncMock(return_value=SimpleNamespace(success=True, message="scheduled")),
        )
        monkeypatch.setattr(render_service_module, "runtime_settings_service", self.RuntimeSettings(True))
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)
        monkeypatch.setattr(render_service_module, "power_service", fake_power)

        service = render_service_module.RenderService()
        service._shutdown_after_all_tasks_armed = True
        await service._maybe_shutdown_after_all_tasks()

        fake_power.schedule_shutdown_once.assert_awaited_once()
        assert fake_power.schedule_shutdown_once.await_args.args[0] == "all-render-tasks"
        fake_job_manager.append_job_log.assert_awaited_once_with("job-1", "scheduled")

    async def test_unfinished_jobs_arm_without_scheduling(self, monkeypatch):
        from gpstitch.services import render_service as render_service_module

        fake_job_manager = SimpleNamespace(has_unfinished_jobs=AsyncMock(return_value=True))
        fake_power = SimpleNamespace(schedule_shutdown_once=AsyncMock())
        monkeypatch.setattr(render_service_module, "runtime_settings_service", self.RuntimeSettings(True))
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)
        monkeypatch.setattr(render_service_module, "power_service", fake_power)

        service = render_service_module.RenderService()
        await service._maybe_shutdown_after_all_tasks()

        assert service._shutdown_after_all_tasks_armed is True
        fake_power.schedule_shutdown_once.assert_not_awaited()

    async def test_disabled_setting_clears_armed_state(self, monkeypatch):
        from gpstitch.services import render_service as render_service_module

        fake_job_manager = SimpleNamespace(has_unfinished_jobs=AsyncMock(return_value=False))
        fake_power = SimpleNamespace(schedule_shutdown_once=AsyncMock())
        monkeypatch.setattr(render_service_module, "runtime_settings_service", self.RuntimeSettings(False))
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)
        monkeypatch.setattr(render_service_module, "power_service", fake_power)

        service = render_service_module.RenderService()
        service._shutdown_after_all_tasks_armed = True
        await service._maybe_shutdown_after_all_tasks()

        assert service._shutdown_after_all_tasks_armed is False
        fake_power.schedule_shutdown_once.assert_not_awaited()


class TestRenderRetry:
    """Tests for retrying failed render attempts before final failure."""

    async def test_retry_or_fail_requeues_when_budget_remains(self, monkeypatch):
        from gpstitch.services import render_service as render_service_module

        fake_job_manager = SimpleNamespace(
            reset_job_for_retry=AsyncMock(return_value=True),
            append_job_log=AsyncMock(),
            update_job_status=AsyncMock(),
        )
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)

        retried = await render_service_module.RenderService()._retry_or_fail_job("job-1", "temporary failure")

        assert retried is True
        fake_job_manager.reset_job_for_retry.assert_awaited_once_with("job-1", "temporary failure")
        fake_job_manager.update_job_status.assert_not_awaited()
        fake_job_manager.append_job_log.assert_not_awaited()

    async def test_retry_or_fail_marks_failed_after_budget_exhausted(self, monkeypatch):
        from gpstitch.models.job import JobStatus
        from gpstitch.services import render_service as render_service_module

        fake_job_manager = SimpleNamespace(
            reset_job_for_retry=AsyncMock(return_value=False),
            append_job_log=AsyncMock(),
            update_job_status=AsyncMock(),
        )
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)

        retried = await render_service_module.RenderService()._retry_or_fail_job("job-1", "permanent failure")

        assert retried is False
        fake_job_manager.reset_job_for_retry.assert_awaited_once_with("job-1", "permanent failure")
        assert [call.args for call in fake_job_manager.append_job_log.await_args_list] == [
            ("job-1", "\n=== Failed ==="),
            ("job-1", "permanent failure"),
        ]
        fake_job_manager.update_job_status.assert_awaited_once_with(
            "job-1",
            JobStatus.FAILED,
            "permanent failure",
        )


class TestLocalSessionRestore:
    """Tests for restoring local sessions needed by retried jobs."""

    async def test_restore_local_session_files_from_persisted_command_log(self, monkeypatch, temp_dir):
        from gpstitch.models.job import RenderJobConfig
        from gpstitch.models.schemas import FileRole
        from gpstitch.services import render_service as render_service_module

        video = temp_dir / "DJI_20260509161038_0080_D.MP4"
        output = temp_dir / "DJI_20260509161038_0080_D_overlay.mp4"
        gpx = temp_dir / "05090802.GPX"
        video.write_bytes(b"video")
        gpx.write_text("<gpx />", encoding="utf-8")
        config = RenderJobConfig(
            session_id="local:old-session",
            layout="default-3840x2160",
            output_file=str(output),
        )
        command_log = f"python wrapper.py '{video}' '{output}' --use-gpx-only --gpx '{gpx}'"
        fake_job = SimpleNamespace(session_files=[], log_lines=[command_log])

        fake_job_manager = SimpleNamespace(
            get_job=AsyncMock(return_value=fake_job),
            set_job_session_files=AsyncMock(),
            append_job_log=AsyncMock(),
        )

        class FakeFileManager:
            def __init__(self):
                self.sessions = {}

            def is_local_session(self, session_id):
                return session_id.startswith("local:")

            def get_files(self, session_id):
                return self.sessions.get(session_id, [])

            def restore_local_session(self, session_id, files):
                self.sessions[session_id] = list(files)

        fake_file_manager = FakeFileManager()
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)
        monkeypatch.setattr("gpstitch.services.file_manager.file_manager", fake_file_manager)

        restored = await render_service_module.RenderService()._restore_local_session_files_for_job("job-1", config)

        assert restored is True
        restored_files = fake_file_manager.get_files("local:old-session")
        assert [file.role for file in restored_files] == [FileRole.PRIMARY, FileRole.SECONDARY]
        assert restored_files[0].file_path == str(video)
        assert restored_files[1].file_path == str(gpx)
        fake_job_manager.set_job_session_files.assert_awaited_once()
        fake_job_manager.append_job_log.assert_awaited_once_with("job-1", "Restored local session files for retry")


class TestResolveMtimeForAlignment:
    """Tests for _resolve_mtime_for_alignment method."""

    @pytest.fixture
    def render_service(self):
        from gpstitch.services.render_service import RenderService

        return RenderService()

    @pytest.fixture
    def config(self):
        from gpstitch.models.job import RenderJobConfig

        return RenderJobConfig(
            session_id="test-session",
            layout="default-1920x1080",
            output_file="/tmp/output.mp4",
        )

    def test_auto_mode_with_creation_time(self, render_service, config):
        """Auto mode should return creation_time as Unix timestamp."""
        config.video_time_alignment = "auto"
        creation_time = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == creation_time.timestamp()

    def test_auto_mode_fallback_to_ctime(self, render_service, config):
        """Auto mode should fallback to filestat().ctime when no creation_time."""
        config.video_time_alignment = "auto"

        fake_ctime = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)
        mock_fstat = SimpleNamespace(ctime=fake_ctime)

        with (
            patch(
                "gpstitch.services.renderer._extract_creation_time",
                return_value=None,
            ),
            patch("gopro_overlay.ffmpeg_gopro.filestat", return_value=mock_fstat),
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == fake_ctime.timestamp()

    def test_auto_mode_without_creation_time_uses_dji_filename(self, render_service, config, monkeypatch):
        """DJI files without MP4 creation_time should still use filename start when it matches GPX."""
        config.video_time_alignment = "auto"
        dji_start = datetime.datetime(2026, 5, 5, 9, 15, 23, tzinfo=datetime.UTC)

        mock_secondary = MagicMock()
        mock_secondary.file_type = "gpx"
        mock_secondary.file_path = "/tmp/05050756.GPX"

        from gpstitch.services import file_manager as fm_module

        mock_fm = MagicMock()
        mock_fm.get_secondary_file.return_value = mock_secondary
        mock_fm.get_primary_file.return_value = None
        monkeypatch.setattr(fm_module, "file_manager", mock_fm)

        with (
            patch("gpstitch.services.renderer._extract_creation_time", return_value=None),
            patch("gpstitch.services.renderer._resolve_dji_filename_start_time", return_value=dji_start),
        ):
            ts = render_service._resolve_mtime_for_alignment(
                config,
                "/tmp/DJI_20260505091523_0004_D.MP4",
            )

        assert ts == dji_start.timestamp()

    def test_auto_mode_prefers_dji_filename_over_creation_time(self, render_service, config, monkeypatch):
        """DJI filenames should win before stale MP4 creation_time in all-day GPX renders."""
        config.video_time_alignment = "auto"
        creation_time = datetime.datetime(2026, 5, 5, 9, 26, 47, tzinfo=datetime.UTC)
        dji_start = datetime.datetime(2026, 5, 5, 9, 15, 23, tzinfo=datetime.UTC)

        mock_secondary = MagicMock()
        mock_secondary.file_type = "gpx"
        mock_secondary.file_path = "/tmp/05050756.GPX"

        from gpstitch.services import file_manager as fm_module

        mock_fm = MagicMock()
        mock_fm.get_secondary_file.return_value = mock_secondary
        mock_fm.get_primary_file.return_value = None
        monkeypatch.setattr(fm_module, "file_manager", mock_fm)

        with (
            patch("gpstitch.services.renderer._resolve_dji_filename_start_time", return_value=dji_start),
            patch("gpstitch.services.renderer._extract_creation_time", return_value=creation_time),
            patch("gpstitch.services.renderer._validate_creation_time") as mock_validate,
        ):
            ts = render_service._resolve_mtime_for_alignment(
                config,
                "/tmp/DJI_20260505091523_0004_D.MP4",
            )

        assert ts == dji_start.timestamp()
        mock_validate.assert_not_called()

    def test_manual_mode_with_offset(self, render_service, config):
        """Manual mode should add offset to creation_time timestamp."""
        config.video_time_alignment = "manual"
        config.time_offset_seconds = 60
        creation_time = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == creation_time.timestamp() + 60

    def test_manual_mode_with_negative_offset(self, render_service, config):
        """Manual mode should support negative offsets."""
        config.video_time_alignment = "manual"
        config.time_offset_seconds = -30
        creation_time = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == creation_time.timestamp() - 30

    def test_gpx_timestamps_returns_none(self, render_service, config):
        """GPX-timestamps mode should return None (no mtime change needed)."""
        config.video_time_alignment = "gpx-timestamps"

        ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts is None

    def test_none_alignment_returns_none(self, render_service, config):
        """No alignment should return None."""
        config.video_time_alignment = None

        ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts is None

    def test_file_modified_with_gpx_secondary(self, render_service, config, monkeypatch):
        """file-modified mode with GPX secondary should use GPX start timestamp."""
        config.video_time_alignment = "file-modified"

        mock_secondary = MagicMock()
        mock_secondary.file_type = "gpx"
        mock_secondary.file_path = "/tmp/track.gpx"

        from gpstitch.services import file_manager as fm_module

        mock_fm = MagicMock()
        mock_fm.get_secondary_file.return_value = mock_secondary
        monkeypatch.setattr(fm_module, "file_manager", mock_fm)

        with patch.object(render_service, "_get_gpx_start_timestamp", return_value=1723132380.0):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == 1723132380.0

    def test_file_modified_with_srt_secondary(self, render_service, config, monkeypatch):
        """file-modified mode with SRT secondary should use original video mtime."""
        config.video_time_alignment = "file-modified"

        mock_secondary = MagicMock()
        mock_secondary.file_type = "srt"
        mock_secondary.file_path = "/tmp/telemetry.srt"

        from gpstitch.services import file_manager as fm_module

        mock_fm = MagicMock()
        mock_fm.get_secondary_file.return_value = mock_secondary
        monkeypatch.setattr(fm_module, "file_manager", mock_fm)

        mock_stat = MagicMock()
        mock_stat.st_mtime = 1723132380.0

        with patch("os.stat", return_value=mock_stat):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == 1723132380.0


class TestAmapRenderCommand:
    """AMap final render should use backend JSAPI map rendering."""

    async def test_amap_render_enables_wrapper_without_warning(self, monkeypatch):
        from gpstitch.models.job import RenderJobConfig
        from gpstitch.services import render_service as render_service_module

        captured = {}

        def fake_generate_cli_command(**kwargs):
            captured.update(kwargs)
            return "gpstitch-dashboard input.mp4 output.mp4 --layout xml --layout-xml no-map.xml", []

        fake_job_manager = SimpleNamespace(
            append_job_log=AsyncMock(),
            update_job_status=AsyncMock(),
            get_next_pending_job=AsyncMock(return_value=None),
        )
        fake_amap_settings = SimpleNamespace(
            get_runtime_config=lambda: SimpleNamespace(configured=True, validated=True)
        )
        service = render_service_module.RenderService()

        monkeypatch.setattr(render_service_module, "generate_cli_command", fake_generate_cli_command)
        monkeypatch.setattr(render_service_module, "job_manager", fake_job_manager)
        monkeypatch.setattr("gpstitch.services.amap_settings.amap_settings_service", fake_amap_settings)
        monkeypatch.setattr(service, "_find_gopro_dashboard", lambda: None)

        config = RenderJobConfig(
            session_id="test-session",
            layout="dji-drone-1920x1080",
            output_file="/tmp/output.mp4",
            map_style="amap-jsapi",
        )

        await service.start_render("job-amap", config)

        assert captured["map_style"] is None
        assert captured["amap_render"] is True
        assert captured["amap_map_style"] == "amap-jsapi"
        assert not captured.get("suppress_map_components", False)
        log_lines = [call.args[1] for call in fake_job_manager.append_job_log.await_args_list]
        assert not any(line.startswith("WARNING:") for line in log_lines)
        assert any("AMap JSAPI video rendering enabled" in line for line in log_lines)


class TestNeedsPillarboxUsesSidecarCanvas:
    """_needs_pillarbox must respect canvas dimensions from a custom XML template's sidecar
    JSON. Without this, a custom 4K 4:3 template (3840x2880) was treated as the default
    built-in layout (1920x1080), which scaled the video down."""

    @pytest.fixture
    def render_service(self):
        from gpstitch.services.render_service import RenderService

        return RenderService()

    def _patch_video_probe(self, monkeypatch, width: int, height: int):
        """Stub gopro-overlay video probing to report the given display dimensions."""
        from gpstitch.services import metadata as metadata_mod

        monkeypatch.setattr(metadata_mod, "get_video_rotation", lambda _p: 0)
        monkeypatch.setattr(metadata_mod, "get_display_dimensions", lambda w, h, _r: (w, h))

        fake_rec = SimpleNamespace(video=SimpleNamespace(dimension=SimpleNamespace(x=width, y=height)))

        class FakeFFMPEGGoPro:
            def __init__(self, *_args, **_kwargs):
                pass

            def find_recording(self, _p):
                return fake_rec

        import gopro_overlay.ffmpeg as gp_ffmpeg
        import gopro_overlay.ffmpeg_gopro as gp_ffmpeg_gopro

        monkeypatch.setattr(gp_ffmpeg, "FFMPEG", lambda: MagicMock())
        monkeypatch.setattr(gp_ffmpeg_gopro, "FFMPEGGoPro", FakeFFMPEGGoPro)

    def test_custom_xml_4k_4_3_no_pillarbox(self, render_service, tmp_path, monkeypatch):
        """Video 3840x2880 with custom XML whose sidecar canvas is 3840x2880 → no pillarbox."""
        xml_path = tmp_path / "Osmo6_Walking_4k_4_3.xml"
        xml_path.write_text("<layout></layout>", encoding="utf-8")
        (tmp_path / "Osmo6_Walking_4k_4_3.json").write_text(
            '{"canvas_width": 3840, "canvas_height": 2880}', encoding="utf-8"
        )

        self._patch_video_probe(monkeypatch, 3840, 2880)

        config = MagicMock()
        config.layout = "xml"
        config.layout_xml_path = str(xml_path)

        result = render_service._needs_pillarbox("/fake/video.mp4", config)
        assert result is None, f"Expected no pillarbox (matching aspect), got {result}"

    def test_custom_xml_canvas_different_aspect_pillarboxes_to_sidecar(self, render_service, tmp_path, monkeypatch):
        """16:9 video into a 4:3 sidecar canvas must pillarbox to the sidecar's dims."""
        xml_path = tmp_path / "custom_4_3.xml"
        xml_path.write_text("<layout></layout>", encoding="utf-8")
        (tmp_path / "custom_4_3.json").write_text('{"canvas_width": 3840, "canvas_height": 2880}', encoding="utf-8")

        self._patch_video_probe(monkeypatch, 3840, 2160)

        config = MagicMock()
        config.layout = "xml"
        config.layout_xml_path = str(xml_path)

        result = render_service._needs_pillarbox("/fake/video.mp4", config)
        assert result is not None
        canvas_w, canvas_h, video_w, video_h = result
        assert (canvas_w, canvas_h) == (3840, 2880)
        assert (video_w, video_h) == (3840, 2160)
