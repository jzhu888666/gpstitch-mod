"""Tests for render command profile and DJI metadata handling."""

from gpstitch.models.schemas import FileRole, VideoMetadata
from gpstitch.scripts.gopro_dashboard_wrapper import TS_DJI_META_SOURCE_ARG


def test_generate_cli_command_passes_nvgpu_profile(clean_file_manager, temp_dir, monkeypatch):
    from gpstitch.services.renderer import generate_cli_command

    video = temp_dir / "video.mp4"
    video.write_bytes(b"video")
    session_id = clean_file_manager.create_local_session()
    clean_file_manager.add_file(
        session_id=session_id,
        filename=video.name,
        file_path=str(video),
        file_type="video",
        role=FileRole.PRIMARY,
    )
    monkeypatch.setattr("gpstitch.services.file_manager.file_manager", clean_file_manager)

    command, _ = generate_cli_command(
        session_id=session_id,
        output_file=str(temp_dir / "out.mp4"),
        layout="default-1920x1080",
        ffmpeg_profile="nvgpu",
        language="en",
    )

    assert "--profile nvgpu" in command
    assert "layouts\\en" in command or "layouts/en" in command


def test_generate_cli_command_uses_dji_meta_gps(clean_file_manager, temp_dir, monkeypatch):
    from gpstitch.services.renderer import generate_cli_command

    video = temp_dir / "dji.mp4"
    video.write_bytes(b"video")
    converted_gpx = temp_dir / "dji_meta.gpx"
    converted_gpx.write_text("<gpx />", encoding="utf-8")
    session_id = clean_file_manager.create_local_session()
    clean_file_manager.add_file(
        session_id=session_id,
        filename=video.name,
        file_path=str(video),
        file_type="video",
        role=FileRole.PRIMARY,
        video_metadata=VideoMetadata(
            width=1920,
            height=1080,
            duration_seconds=5,
            frame_count=150,
            frame_rate=30,
            has_gps=False,
            has_dji_meta=True,
            dji_meta_point_count=10,
        ),
    )
    monkeypatch.setattr("gpstitch.services.file_manager.file_manager", clean_file_manager)
    monkeypatch.setattr("gpstitch.services.renderer._convert_dji_meta_to_gpx", lambda path: str(converted_gpx))

    command, temp_files = generate_cli_command(
        session_id=session_id,
        output_file=str(temp_dir / "out.mp4"),
        layout="default-1920x1080",
        language="zh-CN",
    )

    assert "--use-gpx-only" in command
    assert str(converted_gpx) in command
    assert f"{TS_DJI_META_SOURCE_ARG} " in command
    assert str(video) in command
    assert temp_files == [str(converted_gpx)]
