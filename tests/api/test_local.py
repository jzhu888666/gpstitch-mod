"""Tests for local picker and directory listing helpers."""

from pathlib import Path

from gpstitch.api.local import scan_batch_directories, scan_batch_directory


def test_scan_batch_directory_prefers_srt_over_gpx_and_fit(temp_dir):
    video = temp_dir / "clip.mp4"
    video.write_bytes(b"video")
    (temp_dir / "clip.srt").write_text("srt", encoding="utf-8")
    (temp_dir / "clip.gpx").write_text("gpx", encoding="utf-8")
    (temp_dir / "clip.fit").write_bytes(b"fit")

    other = temp_dir / "other.mov"
    other.write_bytes(b"video")
    (temp_dir / "other.gpx").write_text("gpx", encoding="utf-8")

    files = scan_batch_directory(temp_dir)

    by_name = {Path(item.video_path).name: item for item in files}
    assert by_name["clip.mp4"].gpx_path.endswith("clip.srt")
    assert by_name["clip.mp4"].telemetry_type == "srt"
    assert by_name["other.mov"].gpx_path.endswith("other.gpx")


def test_scan_batch_directories_matches_gps_from_separate_folders(temp_dir):
    video_dir_1 = temp_dir / "day1_video"
    video_dir_2 = temp_dir / "day2_video"
    gps_dir = temp_dir / "gps"
    video_dir_1.mkdir()
    video_dir_2.mkdir()
    gps_dir.mkdir()

    (video_dir_1 / "clip_a.mp4").write_bytes(b"video")
    (video_dir_2 / "clip_b.mov").write_bytes(b"video")
    (gps_dir / "clip_a.gpx").write_text("gpx", encoding="utf-8")
    (gps_dir / "clip_b.fit").write_bytes(b"fit")

    files = scan_batch_directories([video_dir_1, video_dir_2], gps_directories=[gps_dir])

    by_name = {Path(item.video_path).name: item for item in files}
    assert by_name["clip_a.mp4"].gpx_path.endswith("clip_a.gpx")
    assert by_name["clip_a.mp4"].telemetry_type == "gpx"
    assert by_name["clip_b.mov"].gpx_path.endswith("clip_b.fit")
    assert by_name["clip_b.mov"].telemetry_type == "fit"


def test_scan_batch_directories_matches_daily_gps_by_video_folder_name(temp_dir):
    video_day_1 = temp_dir / "videos" / "0505"
    video_day_2 = temp_dir / "videos" / "0506"
    gps_dir = temp_dir / "gps"
    video_day_1.mkdir(parents=True)
    video_day_2.mkdir(parents=True)
    gps_dir.mkdir()

    (video_day_1 / "DJI_20260505091523_0004_D.MP4").write_bytes(b"video")
    (video_day_2 / "DJI_20260506091523_0005_D.MP4").write_bytes(b"video")
    (gps_dir / "05050756.GPX").write_text("gpx", encoding="utf-8")
    (gps_dir / "05060756.GPX").write_text("gpx", encoding="utf-8")

    files = scan_batch_directories([video_day_1, video_day_2], gps_directories=[gps_dir])

    by_folder = {Path(item.video_path).parent.name: item for item in files}
    assert by_folder["0505"].gpx_path.endswith("05050756.GPX")
    assert by_folder["0505"].telemetry_type == "gpx"
    assert by_folder["0506"].gpx_path.endswith("05060756.GPX")
    assert by_folder["0506"].telemetry_type == "gpx"


def test_scan_batch_directories_matches_daily_gps_in_selected_name_subfolder(temp_dir):
    video_day = temp_dir / "videos" / "0505"
    gps_root = temp_dir / "gps"
    gps_day = gps_root / "0505"
    video_day.mkdir(parents=True)
    gps_day.mkdir(parents=True)

    (video_day / "DJI_20260505091523_0004_D.MP4").write_bytes(b"video")
    (gps_day / "track.GPX").write_text("gpx", encoding="utf-8")

    files = scan_batch_directories([video_day], gps_directories=[gps_root], recursive=False)

    assert len(files) == 1
    assert files[0].gpx_path.endswith("track.GPX")
    assert files[0].telemetry_type == "gpx"


async def test_list_directories_local_mode_disabled(async_client, temp_dir, monkeypatch):
    monkeypatch.setattr("gpstitch.api.local.settings.local_mode", False)

    response = await async_client.post(
        "/api/local/list-directories",
        json={"directory_paths": [str(temp_dir)], "language": "en"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Local file mode is disabled."


async def test_list_directories_returns_matched_gps_count(async_client, temp_dir, monkeypatch):
    monkeypatch.setattr("gpstitch.api.local.settings.local_mode", True)
    video_dir = temp_dir / "videos"
    gps_dir = temp_dir / "gps"
    video_dir.mkdir()
    gps_dir.mkdir()
    (video_dir / "clip.mp4").write_bytes(b"video")
    (gps_dir / "clip.gpx").write_text("gpx", encoding="utf-8")

    response = await async_client.post(
        "/api/local/list-directories",
        json={
            "directory_paths": [str(video_dir)],
            "gps_directory_paths": [str(gps_dir)],
            "language": "en",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_videos"] == 1
    assert data["total_matched_gps"] == 1
    assert data["files"][0]["gpx_path"].endswith("clip.gpx")


async def test_list_directory_local_mode_disabled(async_client, temp_dir, monkeypatch):
    monkeypatch.setattr("gpstitch.api.local.settings.local_mode", False)

    response = await async_client.post(
        "/api/local/list-directory",
        json={"directory_path": str(temp_dir), "language": "en"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Local file mode is disabled."


async def test_select_file_cancel_is_non_destructive(async_client, monkeypatch):
    monkeypatch.setattr("gpstitch.api.local.settings.local_mode", True)
    monkeypatch.setattr("gpstitch.api.local._open_file_dialog", lambda request: None)

    response = await async_client.post(
        "/api/local/select-file",
        json={"file_kind": "video", "language": "en"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["selected"] is False
    assert data["file_path"] is None
    assert data["message"] == "Selection cancelled."
