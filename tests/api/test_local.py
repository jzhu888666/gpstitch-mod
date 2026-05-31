"""Tests for local picker and directory listing helpers."""

from gpstitch.api.local import scan_batch_directory


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

    by_name = {item.video_path.split("\\")[-1]: item for item in files}
    assert by_name["clip.mp4"].gpx_path.endswith("clip.srt")
    assert by_name["clip.mp4"].telemetry_type == "srt"
    assert by_name["other.mov"].gpx_path.endswith("other.gpx")


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
